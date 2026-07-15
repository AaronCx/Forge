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


# NOTE: the StreamEvent union is defined at the end of the orchestration
# section below so the Phase 9 workflow events can join it.


# --- dynamic orchestration (Phase 9) ---

StageKind = Literal["fanout", "single", "verify", "reduce"]


@dataclass(frozen=True)
class BudgetSpec:
    """Declarative token/wall-clock bounds for a sub-agent (pure data — the
    runtime ``Budget`` in ``loop.py`` carries the mutable counters)."""

    max_tokens: int | None = None
    max_seconds: float | None = None


@dataclass(frozen=True)
class SubAgentSpec:
    """One scoped sub-agent inside a workflow stage.

    ``tools`` is an explicit allowlist of tool names, or the literal string
    ``"inherit"`` to receive the parent session's tools. ``success_criteria``
    is what the verify stage judges the agent's output against.
    """

    role: str
    prompt: str
    tools: list[str] | str = "inherit"
    model: str | None = None
    budget: BudgetSpec | None = None
    success_criteria: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WorkflowStage:
    """A stage of the workflow DAG. ``fanout`` runs its agents in parallel;
    ``verify`` judges producer outputs; ``reduce`` merges them; ``single`` is
    one agent. ``target`` optionally names a dispatch machine."""

    id: str
    kind: StageKind = "single"
    agents: list[SubAgentSpec] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    concurrency: int | None = None
    target: str | None = None


@dataclass(frozen=True)
class WorkflowSpec:
    """A model-planned, human-approved orchestration of sub-agents."""

    title: str
    rationale: str = ""
    stages: list[WorkflowStage] = field(default_factory=list)
    max_concurrent: int = 16
    max_agents_total: int = 200
    worker_model: str | None = None
    verify: bool = True

    @property
    def agent_count(self) -> int:
        return sum(len(s.agents) for s in self.stages)


@dataclass(frozen=True)
class WorkflowPlanProposed:
    """The planner produced a WorkflowSpec — awaiting explicit user consent."""

    spec: WorkflowSpec
    estimated_tokens: int = 0
    kind: str = field(default="workflow_plan_proposed", init=False)


@dataclass(frozen=True)
class WorkflowProgress:
    """Live progress of one stage of an executing workflow."""

    stage_id: str
    agents_running: int = 0
    agents_done: int = 0
    agents_total: int = 0
    tokens_spent: int = 0
    elapsed_seconds: float = 0.0
    kind: str = field(default="workflow_progress", init=False)


@dataclass(frozen=True)
class WorkflowDone:
    """A workflow finished (or failed) — carries the final output."""

    output: Any = None
    status: Literal["completed", "failed", "cancelled"] = "completed"
    tokens_spent: int = 0
    agents_run: int = 0
    kind: str = field(default="workflow_done", init=False)


StreamEvent = (
    TextDelta | ThinkingDelta | ToolUseStart | ToolUseDelta | UsageEvent | TurnDone
    | WorkflowPlanProposed | WorkflowProgress | WorkflowDone
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
