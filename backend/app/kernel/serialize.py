"""JSON (de)serialization for kernel messages — the session event log format.

Round-trips ``KMessage``/``Block`` through plain dicts using each block's
``kind`` discriminator, so durable sessions (Phase 6) and any future persistence
store kernel state losslessly.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.kernel.types import (
    Block,
    ImageBlock,
    KMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)


def block_to_dict(block: Block) -> dict[str, Any]:
    return asdict(block)


def block_from_dict(data: dict[str, Any]) -> Block:
    kind = data.get("kind")
    if kind == "text":
        return TextBlock(text=data.get("text", ""))
    if kind == "image":
        return ImageBlock(
            media_type=data.get("media_type", ""),
            data=data.get("data"),
            url=data.get("url"),
        )
    if kind == "tool_use":
        return ToolUseBlock(
            id=data.get("id", ""), name=data.get("name", ""), input=data.get("input", {})
        )
    if kind == "tool_result":
        return ToolResultBlock(
            tool_use_id=data.get("tool_use_id", ""),
            output=data.get("output", ""),
            is_error=data.get("is_error", False),
        )
    if kind == "thinking":
        return ThinkingBlock(text=data.get("text", ""))
    # Unknown block kind — preserve as text so nothing is silently dropped.
    return TextBlock(text=str(data))


def message_to_dict(message: KMessage) -> dict[str, Any]:
    return {"role": message.role, "blocks": [block_to_dict(b) for b in message.blocks]}


def message_from_dict(data: dict[str, Any]) -> KMessage:
    return KMessage(
        role=data.get("role", "user"),
        blocks=[block_from_dict(b) for b in data.get("blocks", [])],
    )
