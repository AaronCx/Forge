"""Provider API routes — model listing, health, and configuration."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import get_db
from app.providers.registry import create_user_registry
from app.routers.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["providers"])


class ProviderConfigCreate(BaseModel):
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    is_default: bool = False


class ProviderHealthResponse(BaseModel):
    provider: str
    status: str
    latency_ms: float | None = None
    error: str | None = None


class ModelResponse(BaseModel):
    id: str
    name: str
    provider: str
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool = True
    supports_streaming: bool = True


# --- Provider config CRUD ---


@router.post("/providers/configs")
async def save_provider_config(config: ProviderConfigCreate, user=Depends(get_current_user)):  # noqa: B008
    """Save or update a user's provider configuration."""
    data = {
        "user_id": user.id,
        "provider": config.provider,
        "api_key_encrypted": config.api_key or "",  # WARNING: stored as plaintext. Access control relies on Supabase RLS policies.
        "base_url": config.base_url or "",
        "is_default": config.is_default,
        "is_enabled": True,
    }

    # Upsert — update if exists for this user+provider
    result = get_db().table("provider_configs").upsert(
        data, on_conflict="user_id,provider"
    ).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to save config")

    return {"ok": True, "provider": config.provider}


@router.get("/providers/configs")
async def list_provider_configs(user=Depends(get_current_user)):  # noqa: B008
    """List user's provider configs (keys masked)."""
    result = get_db().table("provider_configs").select("*").eq("user_id", user.id).execute()
    configs = result.data or []

    # Mask API keys
    for c in configs:
        key = c.get("api_key_encrypted", "")
        c["api_key_masked"] = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"
        del c["api_key_encrypted"]

    return configs


@router.delete("/providers/configs/{provider}")
async def delete_provider_config(provider: str, user=Depends(get_current_user)):  # noqa: B008
    """Delete a user's provider configuration."""
    get_db().table("provider_configs").delete().eq("user_id", user.id).eq("provider", provider).execute()
    return {"ok": True}


# --- Model listing ---


@router.get("/providers/models", response_model=list[ModelResponse])
async def list_all_models(
    user=Depends(get_current_user),  # noqa: B008
):
    """List all available models across all configured providers."""
    user_registry = await create_user_registry(user.id)
    models = await user_registry.list_all_models()
    return [
        ModelResponse(
            id=m.id,
            name=m.name,
            provider=m.provider,
            context_window=m.context_window,
            max_output_tokens=m.max_output_tokens,
            supports_tools=m.supports_tools,
            supports_streaming=m.supports_streaming,
        )
        for m in models
    ]


@router.get("/providers/models/{provider}", response_model=list[ModelResponse])
async def list_provider_models(
    provider: str,
    user=Depends(get_current_user),  # noqa: B008
):
    """List models for a specific provider."""
    user_registry = await create_user_registry(user.id)
    p = user_registry.get_provider(provider)
    if not p:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")
    models = await p.list_models()
    return [
        ModelResponse(
            id=m.id,
            name=m.name,
            provider=m.provider,
            context_window=m.context_window,
            max_output_tokens=m.max_output_tokens,
            supports_tools=m.supports_tools,
            supports_streaming=m.supports_streaming,
        )
        for m in models
    ]


# --- Health ---


@router.get("/providers/health", response_model=list[ProviderHealthResponse])
async def provider_health(
    user=Depends(get_current_user),  # noqa: B008
):
    """Check health of all configured providers."""
    user_registry = await create_user_registry(user.id)
    results = await user_registry.health_check_all()
    return [
        ProviderHealthResponse(
            provider=h.provider,
            status=h.status,
            latency_ms=h.latency_ms,
            error=h.error,
        )
        for h in results
    ]


# --- Provider info ---


@router.get("/providers")
async def list_providers(
    user=Depends(get_current_user),  # noqa: B008
):
    """List configured providers and the default model.

    The registry seeds `default_model` from `$DEFAULT_MODEL` (defaulting to
    `gpt-4o-mini`) regardless of which providers are actually configured.
    On a fresh local-only stack with only Ollama registered, that produces
    the misleading payload `{"providers": ["ollama"], "default_model": "gpt-4o-mini"}`.
    Validate the default_model is reachable through the registered providers
    and, if not, fall back to the first model the default_provider exposes.
    """
    from app.providers.registry import MODEL_PROVIDER_MAP

    user_registry = await create_user_registry(user.id)
    default_model = user_registry.default_model
    default_provider = user_registry.default_provider
    provider_names = user_registry.provider_names

    def _model_matches_registered_providers(model: str) -> bool:
        # Explicit provider hint, e.g. "ollama/llama3"
        if "/" in model:
            return model.split("/", 1)[0] in provider_names
        # Prefix table (e.g. "gpt-" -> openai)
        for prefix, name in MODEL_PROVIDER_MAP.items():
            if model.startswith(prefix):
                return name in provider_names
        return False

    if default_provider and not _model_matches_registered_providers(default_model):
        provider = user_registry.get_provider(default_provider)
        if provider is not None:
            try:
                models = await provider.list_models()
                if models:
                    default_model = f"{default_provider}/{models[0].name}"
            except Exception:
                # If the provider is offline, leave the seeded default
                # alone — the UI will surface it as misconfigured.
                pass

    return {
        "providers": provider_names,
        "default_model": default_model,
        "default_provider": default_provider,
    }
