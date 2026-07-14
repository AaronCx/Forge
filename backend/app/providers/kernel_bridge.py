"""Conversion helpers between kernel types and provider-native shapes.

Keeps the per-provider ``turn``/``stream_turn`` implementations small: tool-spec
and message conversion, stop-reason mapping, the OpenAI-compatible turn/stream
routines shared by OpenAI/Ollama/Generic, and the ``TurnResult`` → legacy
``LLMResponse`` shim.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from app.kernel.convert import to_openai_messages
from app.kernel.models import get_model_card
from app.kernel.types import (
    ImageBlock,
    KMessage,
    StopReason,
    StreamEvent,
    TextBlock,
    TextDelta,
    ToolResultBlock,
    ToolSpec,
    ToolUseBlock,
    ToolUseDelta,
    ToolUseStart,
    TurnDone,
    TurnResult,
    Usage,
    UsageEvent,
)
from app.providers.base import LLMResponse

# --- stop-reason mapping ---

_OPENAI_STOP: dict[str, StopReason] = {
    "stop": "end",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "content_filter": "error",
}
_ANTHROPIC_STOP: dict[str, StopReason] = {
    "end_turn": "end",
    "max_tokens": "max_tokens",
    "tool_use": "tool_use",
    "stop_sequence": "end",
    "refusal": "error",
}


def stop_from_openai(finish_reason: str | None) -> StopReason:
    return _OPENAI_STOP.get(finish_reason or "", "end")


def stop_from_anthropic(stop_reason: str | None) -> StopReason:
    return _ANTHROPIC_STOP.get(stop_reason or "", "end")


# --- tool-spec conversion ---

_EMPTY_SCHEMA = {"type": "object", "properties": {}}


def tools_to_openai(tools: list[ToolSpec] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema or _EMPTY_SCHEMA,
            },
        }
        for t in tools
    ]


def tools_to_anthropic(tools: list[ToolSpec] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema or _EMPTY_SCHEMA,
        }
        for t in tools
    ]


# --- kernel -> Anthropic messages (native tool_use/tool_result/image blocks) ---


def _anthropic_content(blocks: list[Any]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for b in blocks:
        if isinstance(b, TextBlock):
            content.append({"type": "text", "text": b.text})
        elif isinstance(b, ImageBlock):
            if b.data is not None:
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": b.media_type or "image/png",
                            "data": b.data,
                        },
                    }
                )
            elif b.url:
                content.append({"type": "image", "source": {"type": "url", "url": b.url}})
        elif isinstance(b, ToolUseBlock):
            content.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        elif isinstance(b, ToolResultBlock):
            out = b.output if isinstance(b.output, list | dict) else str(b.output)
            content.append(
                {"type": "tool_result", "tool_use_id": b.tool_use_id, "content": out,
                 "is_error": b.is_error}
            )
        # ThinkingBlock is output-only; never sent back to the model.
    return content


def kmessages_to_anthropic(
    messages: list[KMessage],
) -> tuple[str, list[dict[str, Any]]]:
    """Return (system_prompt, anthropic_messages).

    The kernel's ``tool`` role has no Anthropic equivalent — tool results ride in
    ``user`` turns. Consecutive same-role turns are merged to satisfy Anthropic's
    strict user/assistant alternation.
    """
    system_parts: list[str] = []
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            text = "".join(b.text for b in m.blocks if isinstance(b, TextBlock))
            if text:
                system_parts.append(text)
            continue
        role = "user" if m.role == "tool" else m.role
        content = _anthropic_content(m.blocks)
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(content)
        else:
            out.append({"role": role, "content": content})
    return "\n\n".join(system_parts), out


# --- OpenAI-compatible turn / stream_turn (shared by OpenAI/Ollama/Generic) ---


def _parse_openai_tool_calls(tool_calls: Any) -> list[ToolUseBlock]:
    blocks: list[ToolUseBlock] = []
    for tc in tool_calls or []:
        fn = tc.function
        raw = fn.arguments
        try:
            args = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
        except (json.JSONDecodeError, TypeError):
            args = {"__raw__": raw}
        blocks.append(ToolUseBlock(id=tc.id or "", name=fn.name or "", input=args or {}))
    return blocks


def tools_unsupported_error(model: str, provider_name: str) -> TurnResult:
    """A clear error TurnResult for a tools request against a tools=False model."""
    return TurnResult(
        blocks=[
            TextBlock(
                f"Model '{model}' on provider '{provider_name}' does not support "
                "tool calling. Choose a tools-capable model or remove the tools."
            )
        ],
        stop_reason="error",
        usage=Usage(),
        model=model,
        provider=provider_name,
    )


def _tools_blocked(model: str, tools: list[ToolSpec] | None) -> bool:
    """True only when tools were requested and a known card says tools=False."""
    if not tools:
        return False
    card = get_model_card(model)
    return card is not None and not card.tools


async def openai_style_turn(
    client: Any,
    provider_name: str,
    messages: list[KMessage],
    model: str,
    *,
    tools: list[ToolSpec] | None,
    temperature: float,
    max_tokens: int,
) -> TurnResult:
    if _tools_blocked(model, tools):
        return tools_unsupported_error(model, provider_name)

    start = time.monotonic()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": to_openai_messages(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    openai_tools = tools_to_openai(tools)
    if openai_tools:
        kwargs["tools"] = openai_tools

    response = await client.chat.completions.create(**kwargs)
    elapsed = (time.monotonic() - start) * 1000

    choice = response.choices[0]
    blocks: list[Any] = []
    if choice.message.content:
        blocks.append(TextBlock(choice.message.content))
    blocks.extend(_parse_openai_tool_calls(getattr(choice.message, "tool_calls", None)))

    usage = response.usage
    return TurnResult(
        blocks=blocks,
        stop_reason=stop_from_openai(choice.finish_reason),
        usage=Usage(
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        ),
        model=getattr(response, "model", model) or model,
        provider=provider_name,
        latency_ms=elapsed,
    )


async def openai_style_stream_turn(
    client: Any,
    provider_name: str,
    messages: list[KMessage],
    model: str,
    *,
    tools: list[ToolSpec] | None,
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[StreamEvent]:
    if _tools_blocked(model, tools):
        yield TurnDone(turn=tools_unsupported_error(model, provider_name))
        return

    start = time.monotonic()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": to_openai_messages(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    openai_tools = tools_to_openai(tools)
    if openai_tools:
        kwargs["tools"] = openai_tools

    text_parts: list[str] = []
    # tool call accumulation keyed by streamed index
    tool_acc: dict[int, dict[str, str]] = {}
    tool_started: set[int] = set()
    finish_reason: str | None = None
    usage = Usage()

    stream = await client.chat.completions.create(**kwargs)
    async for chunk in stream:
        if getattr(chunk, "usage", None):
            usage = Usage(
                input_tokens=chunk.usage.prompt_tokens or 0,
                output_tokens=chunk.usage.completion_tokens or 0,
            )
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        delta = choice.delta
        if getattr(delta, "content", None):
            text_parts.append(delta.content)
            yield TextDelta(text=delta.content)
        for tc in getattr(delta, "tool_calls", None) or []:
            idx = tc.index
            slot = tool_acc.setdefault(idx, {"id": "", "name": "", "args": ""})
            if tc.id:
                slot["id"] = tc.id
            fn = getattr(tc, "function", None)
            if fn and getattr(fn, "name", None):
                slot["name"] = fn.name
            if idx not in tool_started and slot["id"] and slot["name"]:
                tool_started.add(idx)
                yield ToolUseStart(id=slot["id"], name=slot["name"])
            if fn and getattr(fn, "arguments", None):
                slot["args"] += fn.arguments
                yield ToolUseDelta(partial_json=fn.arguments)
        if choice.finish_reason:
            finish_reason = choice.finish_reason

    if usage.input_tokens or usage.output_tokens:
        yield UsageEvent(usage=usage)

    blocks: list[Any] = []
    text = "".join(text_parts)
    if text:
        blocks.append(TextBlock(text))
    for idx in sorted(tool_acc):
        slot = tool_acc[idx]
        try:
            args = json.loads(slot["args"]) if slot["args"] else {}
        except json.JSONDecodeError:
            args = {"__raw__": slot["args"]}
        blocks.append(ToolUseBlock(id=slot["id"], name=slot["name"], input=args))

    turn = TurnResult(
        blocks=blocks,
        stop_reason=stop_from_openai(finish_reason),
        usage=usage,
        model=model,
        provider=provider_name,
        latency_ms=(time.monotonic() - start) * 1000,
    )
    yield TurnDone(turn=turn)


# --- shim: TurnResult -> legacy LLMResponse ---


def turn_result_to_llm_response(turn: TurnResult) -> LLMResponse:
    """Collapse a kernel TurnResult into the legacy LLMResponse (text only)."""
    # Reverse-map to a legacy finish_reason string for callers that inspect it.
    legacy_finish = {
        "end": "stop",
        "max_tokens": "length",
        "tool_use": "tool_calls",
        "error": "error",
    }.get(turn.stop_reason, "stop")
    return LLMResponse(
        content=turn.text,
        model=turn.model,
        input_tokens=turn.usage.input_tokens,
        output_tokens=turn.usage.output_tokens,
        finish_reason=legacy_finish,
        latency_ms=turn.latency_ms,
        provider=turn.provider,
    )


def default_turn_blocks_from_text(text: str) -> list[Any]:
    """Blocks for a text-only TurnResult (used by the base-class default)."""
    return [TextBlock(text)] if text else []


__all__ = [
    "default_turn_blocks_from_text",
    "kmessages_to_anthropic",
    "openai_style_stream_turn",
    "openai_style_turn",
    "stop_from_anthropic",
    "stop_from_openai",
    "tools_to_anthropic",
    "tools_to_openai",
    "tools_unsupported_error",
    "turn_result_to_llm_response",
]
