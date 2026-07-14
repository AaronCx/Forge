"""Model cards — data-driven model knowledge, loaded from ``models.json``.

Model names, context windows, and capabilities live in data, never in Python
constants (harness-plan.md guardrail 5). ``load_model_cards`` is pure: it reads
the bundled JSON and optionally merges a list of per-user override dicts. The
database read that produces those overrides stays in the service/router layer so
the kernel imports nothing app-specific.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from functools import lru_cache
from pathlib import Path
from typing import Any

_MODELS_PATH = Path(__file__).parent / "models.json"


@dataclass(frozen=True)
class ModelCard:
    id: str
    provider: str
    display_name: str
    context_window: int
    max_output: int
    vision: bool = False
    tools: bool = True
    thinking: bool = False
    family: str = ""
    # Optional pricing (USD per 1M tokens); populated for cost budgeting in
    # later phases. None means "unknown — do not price".
    input_price_per_1m: float | None = None
    output_price_per_1m: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_CARD_FIELDS = {f.name for f in fields(ModelCard)}


def _card_from_dict(raw: dict[str, Any]) -> ModelCard:
    """Build a ModelCard from a raw dict, ignoring unknown keys."""
    known = {k: v for k, v in raw.items() if k in _CARD_FIELDS}
    return ModelCard(**known)


@lru_cache(maxsize=1)
def _base_cards() -> dict[str, ModelCard]:
    raw = json.loads(_MODELS_PATH.read_text(encoding="utf-8"))
    cards = {}
    for entry in raw["models"]:
        card = _card_from_dict(entry)
        cards[card.id] = card
    return cards


def load_base_model_cards() -> dict[str, ModelCard]:
    """Return the bundled model cards keyed by id (a fresh copy)."""
    return dict(_base_cards())


def load_model_cards(
    overrides: list[dict[str, Any]] | None = None,
) -> dict[str, ModelCard]:
    """Return base model cards merged with per-user override dicts.

    Each override dict must carry at least ``id``; it replaces or adds the card
    with that id. Overrides missing required fields (provider/display_name/
    context_window/max_output) fall back to the base card's values when one
    exists, so a partial override (e.g. just a display_name tweak) is allowed.
    """
    cards = load_base_model_cards()
    for raw in overrides or []:
        model_id = raw.get("id")
        if not model_id:
            continue
        base = cards.get(model_id)
        merged: dict[str, Any] = base.to_dict() if base else {}
        merged.update({k: v for k, v in raw.items() if k in _CARD_FIELDS})
        # Skip a brand-new card that lacks the required fields.
        required = ("id", "provider", "display_name", "context_window", "max_output")
        if any(merged.get(r) is None for r in required):
            continue
        cards[model_id] = _card_from_dict(merged)
    return cards


def get_model_card(
    model_id: str, overrides: list[dict[str, Any]] | None = None
) -> ModelCard | None:
    return load_model_cards(overrides).get(model_id)
