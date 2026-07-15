"""User provider-key resolution — the single key path.

Every model call now goes through the provider registry (Phase 8 removed the
legacy per-provider SDK client). This module resolves a user's decrypted
provider key (falling back to the matching env var) for the registry and
transcription.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
}


async def get_user_provider_key(user_id: str | None, provider: str = "openai") -> str | None:
    """Resolve a user's API key for ``provider``, or None.

    Resolution order: the user's enabled provider config, then the provider's
    env var. This is the single key path shared by the registry, the dispatcher,
    and transcription.
    """
    api_key = os.getenv(_PROVIDER_ENV.get(provider, ""), "")

    if user_id:
        try:
            from app.db import get_db

            result = (
                get_db().table("provider_configs")
                .select("api_key_encrypted")
                .eq("user_id", user_id)
                .eq("provider", provider)
                .eq("is_enabled", True)
                .single()
                .execute()
            )
            if result.data and result.data.get("api_key_encrypted"):
                from app.services.security.secrets import decrypt_secret

                api_key = decrypt_secret(result.data["api_key_encrypted"])
        except Exception:
            logger.debug("No user %s provider config for %s", provider, user_id, exc_info=True)

    return api_key or None


async def get_user_openai_key(user_id: str | None) -> str | None:
    """Backwards-compatible OpenAI key accessor (delegates to the generic path)."""
    return await get_user_provider_key(user_id, "openai")
