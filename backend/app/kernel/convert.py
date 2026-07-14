"""Lossless converters between OpenAI chat messages and kernel messages.

These let existing string-content and OpenAI-shaped callers enter the kernel
world (and results leave it) without dropping tool calls, tool results, or
images — the exact losses the legacy provider layer suffered.

OpenAI shapes handled:
- ``{"role": "system"|"user"|"assistant", "content": str}``
- ``{"role": "user", "content": [{"type": "text", ...}, {"type": "image_url", ...}]}``
- ``{"role": "assistant", "content": str|None, "tool_calls": [{"id", "function": {...}}]}``
- ``{"role": "tool", "tool_call_id": ..., "content": ...}``
"""

from __future__ import annotations

import json
from typing import Any

from app.kernel.types import (
    Block,
    ImageBlock,
    KMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)


def _image_block_from_url(url: str) -> ImageBlock:
    """Parse a data: URI into media_type + base64 data; keep http(s) as url."""
    if url.startswith("data:"):
        header, _, data = url.partition(",")
        media_type = header[len("data:") :].split(";", 1)[0]
        return ImageBlock(media_type=media_type, data=data)
    return ImageBlock(url=url)


def _image_block_to_url(block: ImageBlock) -> str:
    if block.data is not None:
        return f"data:{block.media_type};base64,{block.data}"
    return block.url or ""


def _content_blocks_from_openai(content: Any) -> list[Block]:
    """Convert an OpenAI ``content`` value (str or block list) to kernel blocks."""
    if content is None:
        return []
    if isinstance(content, str):
        return [TextBlock(text=content)] if content else []
    blocks: list[Block] = []
    for part in content:
        if not isinstance(part, dict):
            blocks.append(TextBlock(text=str(part)))
            continue
        ptype = part.get("type")
        if ptype == "text":
            blocks.append(TextBlock(text=part.get("text", "")))
        elif ptype == "image_url":
            url = part.get("image_url", {}).get("url", "")
            blocks.append(_image_block_from_url(url))
        else:
            blocks.append(TextBlock(text=json.dumps(part)))
    return blocks


def from_openai_messages(messages: list[dict[str, Any]]) -> list[KMessage]:
    """Convert OpenAI chat messages to kernel messages."""
    result: list[KMessage] = []
    for msg in messages:
        role = msg.get("role", "user")
        if role == "tool":
            result.append(
                KMessage(
                    role="tool",
                    blocks=[
                        ToolResultBlock(
                            tool_use_id=msg.get("tool_call_id", ""),
                            output=msg.get("content", ""),
                        )
                    ],
                )
            )
            continue

        blocks = _content_blocks_from_openai(msg.get("content"))
        for call in msg.get("tool_calls") or []:
            fn = call.get("function", {})
            raw_args = fn.get("arguments", "")
            try:
                parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except (json.JSONDecodeError, TypeError):
                parsed = {"__raw__": raw_args}
            blocks.append(
                ToolUseBlock(id=call.get("id", ""), name=fn.get("name", ""), input=parsed)
            )
        result.append(KMessage(role=role, blocks=blocks))
    return result


def _openai_content_from_blocks(blocks: list[Block]) -> tuple[Any, list[dict[str, Any]]]:
    """Split kernel blocks into an OpenAI ``content`` value and ``tool_calls``."""
    text_parts: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    has_image = False
    for block in blocks:
        if isinstance(block, TextBlock):
            text_parts.append({"type": "text", "text": block.text})
        elif isinstance(block, ImageBlock):
            has_image = True
            text_parts.append(
                {"type": "image_url", "image_url": {"url": _image_block_to_url(block)}}
            )
        elif isinstance(block, ToolUseBlock):
            tool_calls.append(
                {
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input),
                    },
                }
            )

    # Collapse a single text-only content back to a plain string (the common,
    # lossless-round-trip case); keep the block list when images are present.
    if not has_image and len(text_parts) == 1 and text_parts[0]["type"] == "text":
        content: Any = text_parts[0]["text"]
    elif not text_parts:
        content = None
    else:
        content = text_parts
    return content, tool_calls


def to_openai_messages(messages: list[KMessage]) -> list[dict[str, Any]]:
    """Convert kernel messages back to OpenAI chat messages."""
    result: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "tool":
            for block in msg.blocks:
                if isinstance(block, ToolResultBlock):
                    result.append(
                        {
                            "role": "tool",
                            "tool_call_id": block.tool_use_id,
                            "content": block.output,
                        }
                    )
            continue

        content, tool_calls = _openai_content_from_blocks(msg.blocks)
        out: dict[str, Any] = {"role": msg.role, "content": content}
        if tool_calls:
            out["tool_calls"] = tool_calls
        result.append(out)
    return result
