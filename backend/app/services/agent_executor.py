import logging
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

from app.providers.registry import provider_registry
from app.services.security.url_validator import SSRFError, validate_url

logger = logging.getLogger(__name__)

load_dotenv()


def _model_supports_vision(model: str | None) -> bool:
    """True if a model's ModelCard advertises vision (image) support."""
    from app.kernel.models import get_model_card

    card = get_model_card(model or "")
    return bool(card and card.vision)


class AgentRunner:
    """Runs agent workflows on the Forge-native kernel loop (any provider, any tool)."""

    def __init__(
        self,
        model: str | None = None,
        user_id: str | None = None,
        *,
        recorder: Any = None,
        response_cache: Any = None,
    ):
        self.model = model or provider_registry.default_model
        self.user_id = user_id
        # Time-travel debugger hooks. ``recorder`` appends to the run's
        # append-only event log; ``response_cache`` serves recorded model/tool
        # responses so replay/fork don't re-pay. Both default to no-ops so the
        # normal execution path is unchanged when the debugger isn't in use.
        from app.services.timetravel.recorder import NullRecorder

        self.recorder = recorder or NullRecorder()
        self.response_cache = response_cache
        # Tracks the workflow step currently executing, so model/tool calls are
        # recorded against the right step without threading it through every call.
        self._current_step = 0

    async def _resolve_tools_native(self, tool_names: list[str], user_id: str | None):
        """Map tool-name strings to ToolPlane ToolSpecs (kernel loop, Phase 4).

        MCP names pass through when the plane has them registered (Phase 5);
        unknown names are dropped with a debug log rather than failing the run.
        """
        from app.kernel.toolplane import ExecContext, tool_plane

        if not tool_names:
            return []
        specs = await tool_plane.list_tools(
            user_id or "", ExecContext(user_id=user_id or "")
        )
        by_name = {s.name: s for s in specs}
        resolved = []
        for name in tool_names:
            spec = by_name.get(name)
            if spec is not None:
                resolved.append(spec)
            else:
                logger.debug("native loop: tool %s not found in plane", name)
        return resolved

    async def _execute_native(
        self,
        agent_config: dict,
        user_input: str,
        *,
        heartbeat_id: str | None = None,
        run_id: str | None = None,
        user_id: str | None = None,
        attachments: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Kernel-loop implementation of execute() — see execute() for the flag."""
        from app.kernel.loop import Budget, ToolExecuted, run_agent_turn
        from app.kernel.toolplane import ExecContext, tool_plane
        from app.kernel.types import (
            KMessage,
            TextBlock,
            ThinkingDelta,
            ToolUseStart,
            TurnDone,
            UsageEvent,
        )
        from app.providers.registry import create_user_registry, provider_registry
        from app.services.heartbeat import heartbeat_service
        from app.services.observability.trace_service import trace_service
        from app.services.tailoring import load_custom_instructions, prepend_about

        uid = user_id or self.user_id
        system_prompt = prepend_about(
            agent_config.get("system_prompt", ""), load_custom_instructions(uid)
        )
        tool_names = agent_config.get("tools", [])
        workflow_steps = agent_config.get("workflow_steps") or [
            "Process the user's input according to your instructions."
        ]
        agent_id = agent_config.get("id")
        model = agent_config.get("model") or self.model

        doc_context, image_blocks, notes = await self._prepare_attachments(attachments, model)
        registry = await create_user_registry(uid) if uid else provider_registry
        specs = await self._resolve_tools_native(tool_names, uid)
        ctx = ExecContext(
            user_id=uid or "",
            run_id=run_id or "",
            workspace_root=agent_config.get("workspace_root", ""),
        )

        if heartbeat_id:
            heartbeat_service.update(heartbeat_id, state="running", current_step=0)
        self._current_step = 0
        self.recorder.run_start(
            agent_id=agent_id, user_input=user_input, model=model, attachments=attachments
        )

        yield {"type": "step", "content": f"Starting agent: {agent_config.get('name', 'Unnamed')}", "tokens": 0}
        for note in notes:
            yield {"type": "step", "content": note, "tokens": 0}

        accumulated_context = doc_context
        if notes:
            accumulated_context = (accumulated_context + "\n\n" + "\n".join(notes)).strip()
        total_tokens = 0
        budget = Budget()

        for i, step in enumerate(workflow_steps, 1):
            self._current_step = i
            self.recorder.step_boundary(i, step)
            yield {"type": "step", "content": f"Step {i}: {step}", "tokens": 0}
            if heartbeat_id:
                heartbeat_service.update(heartbeat_id, state="running", current_step=i)

            step_text = ""
            step_tokens = 0
            final_provider = None
            step_images = image_blocks if i == 1 else None

            if specs:
                # Tools present → run the kernel loop (any provider, streamed).
                full_input = user_input
                if accumulated_context:
                    full_input = f"{user_input}\n\nPrevious step results:\n{accumulated_context}"
                user_blocks: list = [TextBlock(full_input)]
                user_blocks.extend(self._kernel_image_blocks(step_images or []))
                messages = [
                    KMessage(role="system",
                             blocks=[TextBlock(f"{system_prompt}\n\nCurrent task: {step}")]),
                    KMessage(role="user", blocks=user_blocks),
                ]
                async for ev in run_agent_turn(
                    messages, specs, model, registry=registry, plane=tool_plane,
                    ctx=ctx, recorder=self.recorder, budget=budget, step=i,
                ):
                    if isinstance(ev, ThinkingDelta):
                        yield {"type": "thinking", "content": ev.text, "tokens": 0}
                    elif isinstance(ev, ToolUseStart):
                        yield {"type": "tool_use", "id": ev.id, "name": ev.name, "tokens": 0}
                    elif isinstance(ev, UsageEvent):
                        yield {"type": "usage",
                               "input_tokens": ev.usage.input_tokens,
                               "output_tokens": ev.usage.output_tokens,
                               "tokens": ev.usage.input_tokens + ev.usage.output_tokens}
                    elif isinstance(ev, ToolExecuted):
                        yield {"type": "tool_result", "tool": ev.tool_use.name,
                               "output": str(ev.result.output)[:2000],
                               "is_error": ev.result.is_error, "tokens": 0}
                    elif isinstance(ev, TurnDone) and ev.turn.stop_reason != "tool_use":
                        step_text = ev.turn.text
                        step_tokens = ev.turn.usage.input_tokens + ev.turn.usage.output_tokens
                        final_provider = ev.turn.provider
            else:
                # No tools → a single cache-aware model call (preserves the
                # time-travel record/replay/fork seam).
                result = await self._model_call(
                    system_prompt, step, user_input, accumulated_context, model, step_images
                )
                step_text = result["content"]
                step_tokens = result["tokens"]
                final_provider = result.get("provider")
            total_tokens += step_tokens

            if uid:
                try:
                    await trace_service.record_span(
                        user_id=uid, span_type="agent_step",
                        span_name=f"Step {i}: {step[:100]}", run_id=run_id,
                        agent_id=agent_id, model=model, provider=final_provider,
                        input_tokens=0, output_tokens=step_tokens,
                        input_preview=user_input[:500], output_preview=step_text[:500],
                    )
                except Exception:
                    logger.warning("trace span failed on native step %s", i, exc_info=True)
            if uid and run_id and agent_id:
                try:
                    from app.services.token_tracker import token_tracker

                    token_tracker.record(
                        run_id=run_id, agent_id=agent_id, user_id=uid, step_number=i,
                        model=model or "unknown", provider=final_provider or "unknown",
                        input_tokens=0, output_tokens=step_tokens,
                    )
                except Exception:
                    logger.warning("token tracking failed on native step %s", i, exc_info=True)
            if heartbeat_id:
                heartbeat_service.update(
                    heartbeat_id, tokens_used=total_tokens, output_preview=step_text[:500]
                )

            accumulated_context += f"\n\n--- Step {i} result ---\n{step_text}"
            self.recorder.state(i, key="accumulated_context", value=accumulated_context)
            yield {"type": "token", "content": step_text, "tokens": step_tokens}
            yield {"type": "step", "content": f"Step {i} completed", "tokens": 0}

        self.recorder.run_end(status="completed", output=accumulated_context, total_tokens=total_tokens)
        if heartbeat_id:
            heartbeat_service.complete(heartbeat_id, tokens_used=total_tokens)

    @staticmethod
    def _kernel_image_blocks(image_blocks: list[dict]) -> list:
        """Convert OpenAI-format image dicts to kernel ImageBlocks."""
        from app.kernel.convert import _image_block_from_url

        blocks = []
        for ib in image_blocks or []:
            url = ib.get("image_url", {}).get("url", "")
            if url:
                blocks.append(_image_block_from_url(url))
        return blocks

    async def _model_call(
        self,
        system_prompt: str,
        step: str,
        user_input: str,
        context: str,
        model: str | None,
        image_blocks: list[dict] | None = None,
    ) -> dict[str, Any]:
        """A single cache-aware model call via the provider registry (no tools).

        Serves recorded responses from ``response_cache`` (so time-travel replay
        and fork don't re-pay), and records each real call via
        ``recorder.model_call`` for the append-only event log.
        """
        if self.response_cache is not None:
            hit, cached = self.response_cache.get_model(self._current_step)
            if hit:
                return dict(cached)

        full_input = user_input
        if context:
            full_input = f"{user_input}\n\nPrevious step results:\n{context}"
        user_content: Any = full_input
        if image_blocks:
            user_content = [{"type": "text", "text": full_input}, *image_blocks]
        messages = [
            {"role": "system", "content": f"{system_prompt}\n\nCurrent task: {step}"},
            {"role": "user", "content": user_content},
        ]
        request = {"messages": messages, "model": model}

        from app.providers.registry import create_user_registry

        registry = await create_user_registry(self.user_id) if self.user_id else provider_registry
        response = await registry.complete(messages=messages, model=model, temperature=0)
        out = {
            "content": response.content,
            "tokens": response.input_tokens + response.output_tokens,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "latency_ms": response.latency_ms,
            "model": response.model,
            "provider": response.provider,
        }
        self.recorder.model_call(self._current_step, request=request, response=out)
        return out

    async def execute(
        self,
        agent_config: dict,
        user_input: str,
        *,
        heartbeat_id: str | None = None,
        run_id: str | None = None,
        user_id: str | None = None,
        attachments: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Execute an agent's workflow on the Forge-native kernel loop."""
        async for event in self._execute_native(
            agent_config, user_input, heartbeat_id=heartbeat_id,
            run_id=run_id, user_id=user_id, attachments=attachments,
        ):
            yield event

    async def _prepare_attachments(
        self, attachments: list[dict] | None, model: str | None
    ) -> tuple[str, list[dict], list[str]]:
        """Turn attachments into (document_context, image_blocks, notes).

        - Documents are extracted to text and concatenated with a
          ``--- file: {name} ---`` header.
        - Images become OpenAI-style ``image_url`` content blocks for
          vision-capable models, or a ``[image omitted ...]`` note otherwise.
        """
        if not attachments:
            return "", [], []

        from app.services.extract import extract_text

        vision = _model_supports_vision(model)
        doc_parts: list[str] = []
        image_blocks: list[dict] = []
        notes: list[str] = []

        for att in attachments:
            kind = att.get("kind")
            name = att.get("name") or att.get("url", "")
            url = att.get("url", "")
            if not url:
                continue

            if kind == "image":
                if vision:
                    image_blocks.append({"type": "image_url", "image_url": {"url": url}})
                else:
                    notes.append(f"[image omitted: model not multimodal] {name}")
            elif kind == "document":
                try:
                    # Remote URLs must pass the SSRF check; local file:// refs
                    # are restricted to the upload dir inside extract_text.
                    if urlparse(url).scheme in ("http", "https"):
                        validate_url(url)
                    text = await extract_text(url)
                    doc_parts.append(f"--- file: {name} ---\n{text}")
                except SSRFError:
                    logger.warning("Blocked attachment URL %s", name)
                    notes.append(f"[document omitted: URL not allowed for {name}]")
                except Exception:
                    logger.warning("Failed to extract attachment %s", name, exc_info=True)
                    notes.append(f"[document omitted: could not read {name}]")

        return "\n\n".join(doc_parts), image_blocks, notes
