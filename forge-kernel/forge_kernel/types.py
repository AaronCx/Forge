"""Kernel types — the provider-neutral vocabulary for agentic exchanges.

Frozen dataclasses (not Pydantic) keep the kernel dependency-light and hashable
intent clear: values are immutable, comparable by value, and trivially
serializable. Content is modeled as a list of typed *blocks* so a single message
can carry text, images, tool calls, tool results, and thinking without lossy
string flattening — the failure mode of the legacy provider layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]
StopReason = Literal["end", "tool_use", "max_tokens", "error"]
DangerLevel = Literal["safe", "caution", "dangerous"]
ToolSource = Literal["builtin", "mcp", "blueprint", "computer_use", "workspace"]


# --- content blocks ---


@dataclass(frozen=True)
class TextBlock:
    text: str
    kind: str = field(default="text", init=False)


@dataclass(frozen=True)
class ImageBlock:
    """An image, either inline base64 (``data`` + ``media_type``) or by ``url``."""

    media_type: str = ""
    data: str | None = None
    url: str | None = None
    kind: str = field(default="image", init=False)


@dataclass(frozen=True)
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)
    kind: str = field(default="tool_use", init=False)


@dataclass(frozen=True)
class ToolResultBlock:
    tool_use_id: str
    output: Any = ""
    is_error: bool = False
    kind: str = field(default="tool_result", init=False)


@dataclass(frozen=True)
class ThinkingBlock:
    text: str
    kind: str = field(default="thinking", init=False)


Block = TextBlock | ImageBlock | ToolUseBlock | ToolResultBlock | ThinkingBlock


@dataclass(frozen=True)
class KMessage:
    role: Role
    blocks: list[Block] = field(default_factory=list)


# --- turn results ---


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class TurnResult:
    blocks: list[Block]
    stop_reason: StopReason
    usage: Usage
    model: str
    provider: str
    latency_ms: float = 0.0

    @property
    def text(self) -> str:
        """Concatenated text of all TextBlocks — the legacy ``content`` view."""
        return "".join(b.text for b in self.blocks if isinstance(b, TextBlock))

    @property
    def tool_calls(self) -> list[ToolUseBlock]:
        return [b for b in self.blocks if isinstance(b, ToolUseBlock)]


# --- streaming events ---


@dataclass(frozen=True)
class TextDelta:
    text: str
    kind: str = field(default="text_delta", init=False)


@dataclass(frozen=True)
class ThinkingDelta:
    text: str
    kind: str = field(default="thinking_delta", init=False)


@dataclass(frozen=True)
class ToolUseStart:
    id: str
    name: str
    kind: str = field(default="tool_use_start", init=False)


@dataclass(frozen=True)
class ToolUseDelta:
    partial_json: str
    kind: str = field(default="tool_use_delta", init=False)


@dataclass(frozen=True)
class UsageEvent:
    usage: Usage
    kind: str = field(default="usage", init=False)


@dataclass(frozen=True)
class TurnDone:
    turn: TurnResult
    kind: str = field(default="turn_done", init=False)


StreamEvent = (
    TextDelta | ThinkingDelta | ToolUseStart | ToolUseDelta | UsageEvent | TurnDone
)


# --- tool specifications ---


@dataclass(frozen=True)
class ToolSpec:
    """A single callable capability, from any source, behind one policy.

    ``danger_level`` drives the default permission decision (safe=allow,
    caution/dangerous=ask) when no explicit per-user/per-session policy applies.
    """

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    source: ToolSource = "builtin"
    source_id: str = ""
    requires_approval: bool = False
    danger_level: DangerLevel = "safe"
