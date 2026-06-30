import logging
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv
from langchain.agents import create_agent
from langgraph.errors import GraphRecursionError

from app.mcp.tool_registry import tool_registry
from app.providers.registry import provider_registry
from app.services.security.url_validator import SSRFError, validate_url
from app.services.tools.code_executor import code_executor
from app.services.tools.data_extractor import data_extractor
from app.services.tools.document_reader import document_reader
from app.services.tools.summarizer import summarizer
from app.services.tools.web_search import web_search

logger = logging.getLogger(__name__)

load_dotenv()

# Bound the model<->tool loop. langgraph's recursion_limit is ~2*max_iterations+1;
# this mirrors the legacy AgentExecutor(max_iterations=5) cap that the 1.x
# migration dropped (default was ~5000), preventing runaway tool loops.
_TOOL_RECURSION_LIMIT = 12


def _content_to_text(content: Any) -> str:
    """Coerce a message's content to text. langchain 1.x AIMessage.content may
    be a list of content blocks rather than a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


def _sum_usage(messages: list) -> tuple[int, int]:
    """Sum input/output tokens across AIMessages' usage_metadata."""
    input_tokens = output_tokens = 0
    for msg in messages:
        usage = getattr(msg, "usage_metadata", None)
        if usage:
            input_tokens += usage.get("input_tokens", 0) or 0
            output_tokens += usage.get("output_tokens", 0) or 0
    return input_tokens, output_tokens

TOOL_REGISTRY = {
    "web_search": web_search,
    "document_reader": document_reader,
    "code_executor": code_executor,
    "data_extractor": data_extractor,
    "summarizer": summarizer,
}

# Models that accept OpenAI-style ``image_url`` content blocks. Image
# passthrough is restricted to these so we never hand an Anthropic/Ollama
# model a content schema it can't parse — non-matching models get a text note
# instead (see ``_prepare_attachments``).
_VISION_MODEL_HINTS = ("gpt-4o", "gpt-4.1", "gpt-4-turbo", "gpt-4-vision", "o1")


def _is_vision_capable(model: str | None) -> bool:
    """True if ``model`` accepts OpenAI-style multimodal image content blocks."""
    m = (model or "").lower()
    return any(hint in m for hint in _VISION_MODEL_HINTS)


class AgentRunner:
    """Executes agent workflows step-by-step using LangChain with tool integration."""

    def __init__(
        self,
        model: str | None = None,
        user_id: str | None = None,
        *,
        recorder: Any = None,
        response_cache: Any = None,
    ):
        from langchain_openai import ChatOpenAI

        self.model = model or provider_registry.default_model
        self.user_id = user_id
        self._llm: ChatOpenAI | None = None  # Created lazily
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

    async def _get_llm(self):
        """Get LLM instance, using the shared user-LLM resolver (one key path)."""
        if self._llm:
            return self._llm

        from app.services.llm import get_user_llm

        self._llm = await get_user_llm(self.user_id, self.model, streaming=True, temperature=0)
        return self._llm

    def _resolve_tools(self, tool_names: list[str]):
        """Resolve tool name strings to actual LangChain tool instances.

        Returns a tuple of (langchain_tools, mcp_tool_names) where mcp_tool_names
        are tools that need to be called via MCP rather than locally.
        """
        lc_tools = []
        mcp_tools = []
        for name in tool_names:
            if name in TOOL_REGISTRY:
                lc_tools.append(TOOL_REGISTRY[name])
            elif not tool_registry.is_builtin(name):
                # Could be an MCP tool (format: "server_id:tool_name" or just name)
                mcp_tools.append(name)
        return lc_tools, mcp_tools

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
        """Execute an agent's workflow and yield streaming events."""
        from app.services.heartbeat import heartbeat_service
        from app.services.observability.trace_service import trace_service
        from app.services.tailoring import load_custom_instructions, prepend_about

        system_prompt = agent_config.get("system_prompt", "")
        # Weave the user's global custom instructions into the system prompt at
        # run time (idempotent — a seeded prompt that already carries the block
        # isn't doubled; agents created after onboarding still benefit).
        system_prompt = prepend_about(system_prompt, load_custom_instructions(user_id or self.user_id))
        tool_names = agent_config.get("tools", [])
        workflow_steps = agent_config.get("workflow_steps", [])
        tools, _mcp_tools = self._resolve_tools(tool_names)
        agent_id = agent_config.get("id")

        # Per-agent model override
        model = agent_config.get("model") or self.model

        if not workflow_steps:
            workflow_steps = ["Process the user's input according to your instructions."]

        # Documents become prepended context; images become multimodal blocks
        # (or a note for non-vision models). Done once, up front.
        doc_context, image_blocks, notes = await self._prepare_attachments(attachments, model)

        if heartbeat_id:
            heartbeat_service.update(
                heartbeat_id, state="running", current_step=0
            )

        # Open the run's event log (no-op when no recorder is attached).
        self._current_step = 0
        self.recorder.run_start(
            agent_id=agent_id, user_input=user_input, model=model, attachments=attachments
        )

        yield {"type": "step", "content": f"Starting agent: {agent_config.get('name', 'Unnamed')}", "tokens": 0}
        for note in notes:
            yield {"type": "step", "content": note, "tokens": 0}

        # Seed context with extracted document text + any attachment notes.
        accumulated_context = doc_context
        if notes:
            accumulated_context = (accumulated_context + "\n\n" + "\n".join(notes)).strip()
        total_tokens = 0

        for i, step in enumerate(workflow_steps, 1):
            self._current_step = i
            self.recorder.step_boundary(i, step)
            yield {"type": "step", "content": f"Step {i}: {step}", "tokens": 0}

            if heartbeat_id:
                heartbeat_service.update(
                    heartbeat_id, state="running", current_step=i
                )

            # Only send image blocks on the first step to avoid re-billing the
            # image on every step; later steps carry forward via context.
            step_images = image_blocks if i == 1 else None

            if tools:
                result = await self._execute_with_tools(
                    system_prompt, step, user_input, accumulated_context, tools, image_blocks=step_images,
                )
            else:
                result = await self._execute_step(
                    system_prompt, step, user_input, accumulated_context, model=model, image_blocks=step_images,
                )

            step_tokens = result.get("tokens", 0)
            total_tokens += step_tokens

            # Record trace span for this step
            if user_id:
                try:
                    await trace_service.record_span(
                        user_id=user_id,
                        span_type="agent_step",
                        span_name=f"Step {i}: {step[:100]}",
                        run_id=run_id,
                        agent_id=agent_id,
                        model=result.get("model") or model,
                        provider=result.get("provider"),
                        input_tokens=result.get("input_tokens", 0),
                        output_tokens=result.get("output_tokens", 0),
                        latency_ms=result.get("latency_ms", 0),
                        input_preview=user_input[:500],
                        output_preview=result["content"][:500],
                    )
                except Exception:
                    logger.warning("Failed to record trace span", exc_info=True)

                # Record per-step token usage so /api/costs/* aggregates can
                # see this run. Without this, cost-by-{agent,model,provider}
                # breakdowns return zero on every Ollama-only stack (the
                # blueprint engine writes here but the agent executor didn't
                # — surfaced by QA Findings #27 and #29).
                if run_id and agent_id:
                    try:
                        from app.services.token_tracker import token_tracker

                        token_tracker.record(
                            run_id=run_id,
                            agent_id=agent_id,
                            user_id=user_id,
                            step_number=i,
                            model=result.get("model") or model or "unknown",
                            provider=result.get("provider") or "unknown",
                            input_tokens=result.get("input_tokens", 0),
                            output_tokens=result.get("output_tokens", 0),
                        )
                    except Exception:
                        logger.warning("Failed to record token usage", exc_info=True)

            if heartbeat_id:
                heartbeat_service.update(
                    heartbeat_id,
                    tokens_used=total_tokens,
                    output_preview=result["content"][:500],
                )

            accumulated_context += f"\n\n--- Step {i} result ---\n{result['content']}"
            # Record the post-step accumulated context as a state mutation so the
            # replayer can reconstruct exact step-by-step state from the log.
            self.recorder.state(i, key="accumulated_context", value=accumulated_context)
            yield {"type": "token", "content": result["content"], "tokens": step_tokens}
            yield {"type": "step", "content": f"Step {i} completed", "tokens": 0}

        self.recorder.run_end(status="completed", output=accumulated_context, total_tokens=total_tokens)

        if heartbeat_id:
            heartbeat_service.complete(heartbeat_id, tokens_used=total_tokens)

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

        vision = _is_vision_capable(model)
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

    async def _execute_with_tools(
        self, system_prompt: str, step: str, user_input: str, context: str, tools: list,
        *, image_blocks: list[dict] | None = None,
    ) -> dict:
        """Execute a step using LangChain agent with tools."""
        # Replay/fork: a cached step result is served verbatim — the LangChain
        # executor (and every model/tool call it would make) is skipped, so the
        # step isn't re-billed.
        if self.response_cache is not None:
            hit, cached = self.response_cache.get_model(self._current_step)
            if hit:
                return dict(cached)

        llm = await self._get_llm()
        if not llm:
            # No OpenAI key — fall back to non-tool step via provider registry
            return await self._execute_step(
                system_prompt, step, user_input, context, model=self.model, image_blocks=image_blocks
            )

        # langchain>=1.0: the legacy AgentExecutor/create_openai_tools_agent
        # combo was removed in favour of the prebuilt ``create_agent`` graph,
        # which runs the model<->tool loop internally. It takes a messages-style
        # input and returns ``{"messages": [...]}`` with the final answer in the
        # last AIMessage's ``content`` (vs. the old ``{"output": ...}``).
        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=f"{system_prompt}\n\nCurrent task: {step}",
        )

        full_input = user_input
        if context:
            full_input = f"{user_input}\n\nPrevious step results:\n{context}"

        # Multimodal first message when vision image blocks are present.
        user_content: str | list[dict] = (
            [{"type": "text", "text": full_input}, *image_blocks] if image_blocks else full_input
        )

        request = {"system_prompt": system_prompt, "step": step, "input": full_input, "tools": True}
        try:
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": user_content}]},
                config={"recursion_limit": _TOOL_RECURSION_LIMIT},
            )
        except GraphRecursionError:
            logger.warning(
                "Agent tool loop hit recursion limit (%d) on step %d",
                _TOOL_RECURSION_LIMIT, self._current_step,
            )
            out = {
                "content": "The agent reached its tool-iteration limit before completing this step.",
                "tokens": 0, "input_tokens": 0, "output_tokens": 0,
            }
            self.recorder.model_call(self._current_step, request=request, response=out)
            return out

        messages = result.get("messages", []) if isinstance(result, dict) else []
        content = _content_to_text(messages[-1].content) if messages else ""
        input_tokens, output_tokens = _sum_usage(messages)

        # Record each individual tool invocation so the run event log / timeline
        # captures the model<->tool loop ``create_agent`` runs internally. This
        # is purely additive: an AIMessage carries ``.tool_calls`` (name/args/id)
        # and the matching ToolMessage carries the result via ``.tool_call_id``.
        # Wrapped so a recording failure never breaks the run.
        try:
            self._record_tool_calls(messages)
        except Exception:
            logger.warning("Failed to record tool calls", exc_info=True)

        out = {
            "content": content,
            "tokens": input_tokens + output_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        # Record the tool-augmented step's outcome as a model_call so replay and
        # fork can reconstruct it without re-running the agent loop.
        self.recorder.model_call(self._current_step, request=request, response=out)
        return out

    @staticmethod
    def _field(obj: Any, name: str, default: Any = None) -> Any:
        """Read ``name`` from a langchain message object OR a plain dict."""
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    def _record_tool_calls(self, messages: list) -> None:
        """Record each tool invocation found in ``create_agent``'s messages.

        Walks the returned messages: an AIMessage's ``.tool_calls`` lists the
        invocations (each with ``name``/``args``/``id``) and the matching
        ToolMessage carries the result via ``.tool_call_id``. Messages may be
        langchain objects or dicts, so every field read goes through
        :meth:`_field`. Best-effort — skips anything malformed and no-ops when
        there are no tool calls.
        """
        if not messages:
            return

        # Index tool results by the call id they answer (ToolMessage carries
        # ``tool_call_id`` + ``content``). Some messages expose this only via
        # a ``type`` discriminator, so we key off whatever has a tool_call_id.
        results_by_id: dict[str, Any] = {}
        for msg in messages:
            call_id = self._field(msg, "tool_call_id")
            if call_id is not None:
                results_by_id[str(call_id)] = self._field(msg, "content")

        for msg in messages:
            tool_calls = self._field(msg, "tool_calls") or []
            for call in tool_calls:
                try:
                    name = self._field(call, "name")
                    args = self._field(call, "args", {}) or {}
                    call_id = self._field(call, "id")
                    result = results_by_id.get(str(call_id)) if call_id is not None else None
                    if name is None:
                        continue
                    self.recorder.tool_call(
                        self._current_step, name=name, args=args, result=result
                    )
                except Exception:
                    logger.warning("Failed to record a tool call", exc_info=True)

    async def _execute_step(
        self,
        system_prompt: str,
        step: str,
        user_input: str,
        context: str,
        *,
        model: str | None = None,
        image_blocks: list[dict] | None = None,
    ) -> dict:
        """Execute a single workflow step via the provider registry."""
        full_input = user_input
        if context:
            full_input = f"{user_input}\n\nPrevious step results:\n{context}"

        # When images are present (vision models only), the user message uses
        # multimodal content blocks; otherwise it's a plain string.
        user_content: str | list[dict]
        if image_blocks:
            user_content = [{"type": "text", "text": full_input}, *image_blocks]
        else:
            user_content = full_input

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": f"{system_prompt}\n\nCurrent task: {step}"},
            {"role": "user", "content": user_content},
        ]

        return await self._invoke_model(messages, model)

    async def _invoke_model(self, messages: list[dict[str, Any]], model: str | None) -> dict:
        """Run one model completion, consulting the cache and recording the result.

        This is the single interception point for model calls. When a step's
        response is cached (replay, or a fork's unchanged prefix) the recorded
        value is returned and the provider is never hit — that's how forks avoid
        re-paying. Otherwise the real provider runs and the call is recorded.
        """
        request = {"messages": messages, "model": model}

        if self.response_cache is not None:
            hit, cached = self.response_cache.get_model(self._current_step)
            if hit:
                # Served from the recorded log — do NOT record again (the event
                # already exists in the parent/original log; a fork copies the
                # prefix verbatim before resuming).
                return dict(cached)

        # Use user's provider registry if available
        if self.user_id:
            from app.providers.registry import create_user_registry

            registry = await create_user_registry(self.user_id)
        else:
            registry = provider_registry

        response = await registry.complete(
            messages=messages,
            model=model,
            temperature=0,
        )

        result = {
            "content": response.content,
            "tokens": response.input_tokens + response.output_tokens,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "latency_ms": response.latency_ms,
            "model": response.model,
            "provider": response.provider,
        }
        self.recorder.model_call(self._current_step, request=request, response=result)
        return result
