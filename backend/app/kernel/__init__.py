"""Forge kernel — a provider-neutral representation of agentic exchanges.

Pure types and converters with no I/O, no FastAPI, and no LangChain, so the
kernel can later be extracted as a dependency-light ``forge-kernel`` package
(harness-plan.md Phase 7). Nothing here changes runtime behavior on its own;
provider adapters and the native loop wire it in during later phases.
"""

from app.kernel.types import (
    Block,
    ImageBlock,
    KMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolSpec,
    ToolUseBlock,
    TurnResult,
    Usage,
)

__all__ = [
    "Block",
    "ImageBlock",
    "KMessage",
    "TextBlock",
    "ThinkingBlock",
    "ToolResultBlock",
    "ToolSpec",
    "ToolUseBlock",
    "TurnResult",
    "Usage",
]
