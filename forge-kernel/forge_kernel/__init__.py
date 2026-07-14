"""forge-kernel — a provider-neutral, dependency-light agent kernel.

Extracted from Forge (harness-plan.md Phase 7): the pure types, model cards,
lossless OpenAI converters, and the streamed agent loop — no FastAPI, no
LangChain. Bring your own provider (any object with an async ``stream``) and
tool plane (any object with an async ``execute``).
"""

from forge_kernel.convert import from_openai_messages, to_openai_messages
from forge_kernel.loop import Budget, ToolExecuted, run_agent_turn
from forge_kernel.models import ModelCard, get_model_card, load_model_cards
from forge_kernel.types import (
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

__version__ = "0.1.0"

__all__ = [
    "Budget",
    "ImageBlock",
    "KMessage",
    "ModelCard",
    "TextBlock",
    "ThinkingBlock",
    "ToolExecuted",
    "ToolResultBlock",
    "ToolSpec",
    "ToolUseBlock",
    "TurnResult",
    "Usage",
    "from_openai_messages",
    "get_model_card",
    "load_model_cards",
    "run_agent_turn",
    "to_openai_messages",
]
