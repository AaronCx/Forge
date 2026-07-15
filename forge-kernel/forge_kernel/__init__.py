"""forge-kernel — a provider-neutral, dependency-light agent kernel.

Extracted from Forge (harness-plan.md Phase 7): the pure types, model cards,
lossless OpenAI converters, and the streamed agent loop — no FastAPI, no
LangChain. Bring your own provider (any object with an async ``stream``) and
tool plane (any object with an async ``execute``).
"""

from forge_kernel.convert import from_openai_messages, to_openai_messages
from forge_kernel.loop import Budget, ToolExecuted, run_agent_turn
from forge_kernel.models import ModelCard, get_model_card, load_model_cards
from forge_kernel.serialize import (
    workflow_spec_from_dict,
    workflow_spec_json_schema,
    workflow_spec_to_dict,
)
from forge_kernel.types import (
    BudgetSpec,
    ImageBlock,
    KMessage,
    SubAgentSpec,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolSpec,
    ToolUseBlock,
    TurnResult,
    Usage,
    WorkflowDone,
    WorkflowPlanProposed,
    WorkflowProgress,
    WorkflowSpec,
    WorkflowStage,
)

__version__ = "0.2.0"

__all__ = [
    "Budget",
    "BudgetSpec",
    "ImageBlock",
    "KMessage",
    "ModelCard",
    "SubAgentSpec",
    "TextBlock",
    "ThinkingBlock",
    "ToolExecuted",
    "ToolResultBlock",
    "ToolSpec",
    "ToolUseBlock",
    "TurnResult",
    "Usage",
    "WorkflowDone",
    "WorkflowPlanProposed",
    "WorkflowProgress",
    "WorkflowSpec",
    "WorkflowStage",
    "from_openai_messages",
    "get_model_card",
    "load_model_cards",
    "run_agent_turn",
    "to_openai_messages",
    "workflow_spec_from_dict",
    "workflow_spec_json_schema",
    "workflow_spec_to_dict",
]
