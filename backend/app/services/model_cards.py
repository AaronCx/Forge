"""Per-user model cards — bridges the pure kernel to the database.

The kernel's ``load_model_cards`` is deliberately I/O-free; this service reads
each provider config's ``model_overrides`` JSON column, flattens them, and merges
them over the bundled cards. ``refresh_user_model_cards`` repopulates those
overrides from each registered provider's live ``list_models()``.
"""

from __future__ import annotations

import logging
from typing import Any

from app.db import get_db
from app.kernel.models import ModelCard, load_model_cards
from app.providers.registry import create_user_registry

logger = logging.getLogger(__name__)

# Sensible fallbacks when a provider's list_models() omits metadata, so a newly
# discovered model still satisfies ModelCard's required fields and is included.
_DEFAULT_CONTEXT_WINDOW = 8192
_DEFAULT_MAX_OUTPUT = 4096


def _user_overrides(user_id: str) -> list[dict[str, Any]]:
    """Collect every provider config's model_overrides array for a user."""
    try:
        result = (
            get_db()
            .table("provider_configs")
            .select("model_overrides")
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 - overrides are best-effort
        logger.debug("model_overrides read failed for %s: %s", user_id, exc)
        return []

    overrides: list[dict[str, Any]] = []
    for row in result.data or []:
        value = row.get("model_overrides") or []
        if isinstance(value, list):
            overrides.extend(v for v in value if isinstance(v, dict))
    return overrides


async def get_user_model_cards(user_id: str | None) -> list[ModelCard]:
    """Bundled cards merged with the user's stored overrides."""
    overrides = _user_overrides(user_id) if user_id else []
    return list(load_model_cards(overrides).values())


async def refresh_user_model_cards(user_id: str) -> list[ModelCard]:
    """Pull each registered provider's models and persist them as overrides."""
    registry = await create_user_registry(user_id)
    by_provider: dict[str, list[dict[str, Any]]] = {}

    for provider_name in registry.provider_names:
        provider = registry.get_provider(provider_name)
        if provider is None:
            continue
        try:
            models = await provider.list_models()
        except Exception as exc:  # noqa: BLE001 - one bad provider must not fail all
            logger.warning("list_models failed for %s: %s", provider_name, exc)
            continue
        cards: list[dict[str, Any]] = []
        for m in models:
            cards.append(
                {
                    "id": m.id,
                    "provider": m.provider,
                    "display_name": m.name,
                    "context_window": m.context_window or _DEFAULT_CONTEXT_WINDOW,
                    "max_output": m.max_output_tokens or _DEFAULT_MAX_OUTPUT,
                    "tools": m.supports_tools,
                    "family": m.provider,
                }
            )
        by_provider[provider_name] = cards

    # Persist per provider (best-effort; a missing config row for an env-only
    # provider like the global default is simply skipped by the .eq filter).
    for provider_name, cards in by_provider.items():
        try:
            get_db().table("provider_configs").update({"model_overrides": cards}).eq(
                "user_id", user_id
            ).eq("provider", provider_name).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("persist overrides failed for %s: %s", provider_name, exc)

    flat = [c for cards in by_provider.values() for c in cards]
    return list(load_model_cards(flat).values())
