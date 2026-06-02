"""User LLM resolution — the single provider/key path.

Factored out of ``AgentRunner._get_llm`` so the agent runner, the dispatcher,
and transcription all build their OpenAI client the same way: from the user's
decrypted key in ``provider_configs`` (falling back to the ``OPENAI_API_KEY``
env var). There is no second key path.
"""

from __future__ import annotations

import logging
import os

from langchain_openai import ChatOpenAI

from app.providers.registry import provider_registry

logger = logging.getLogger(__name__)


async def get_user_openai_key(user_id: str | None) -> str | None:
    """Resolve the user's OpenAI API key, or None.

    Resolution order: the user's enabled ``openai`` provider config, then the
    ``OPENAI_API_KEY`` env var. This is the single OpenAI key path shared by the
    runner, the dispatcher, and transcription.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")

    if user_id:
        try:
            from app.db import get_db

            result = (
                get_db().table("provider_configs")
                .select("api_key_encrypted")
                .eq("user_id", user_id)
                .eq("provider", "openai")
                .eq("is_enabled", True)
                .single()
                .execute()
            )
            if result.data and result.data.get("api_key_encrypted"):
                api_key = result.data["api_key_encrypted"]
        except Exception:
            logger.debug("No user openai provider config for %s", user_id, exc_info=True)

    return api_key or None


async def get_user_llm(
    user_id: str | None,
    model: str | None = None,
    *,
    streaming: bool = True,
    temperature: float = 0.0,
) -> ChatOpenAI | None:
    """Build a ChatOpenAI client from the user's OpenAI key, or None.

    Returns None when no OpenAI key is available (callers fall back to the
    provider registry or surface a clear message).
    """
    api_key = await get_user_openai_key(user_id)
    if not api_key:
        return None

    return ChatOpenAI(  # type: ignore[call-arg]
        model=model or provider_registry.default_model,
        temperature=temperature,
        streaming=streaming,
        api_key=api_key,  # type: ignore[arg-type]
    )
