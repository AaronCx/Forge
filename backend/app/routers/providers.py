"""Provider API routes — model listing, health, and configuration."""

import logging
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import get_db
from app.providers.registry import create_user_registry
from app.routers.auth import get_current_user
from app.services.security.secrets import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)
router = APIRouter(tags=["providers"])

DEFAULT_OLLAMA_URL = "http://localhost:11434"


class ProviderConfigCreate(BaseModel):
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    is_default: bool = False


class ProviderVerifyRequest(BaseModel):
    kind: Literal["cloud", "ollama", "generic"]
    provider: str | None = None  # openai | anthropic (for cloud)
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class ProviderConnectRequest(BaseModel):
    kind: Literal["cloud", "ollama", "generic"]
    provider: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


def _build_provider(req: ProviderVerifyRequest | ProviderConnectRequest):
    """Instantiate the right provider class for a verify/connect request."""
    if req.kind == "cloud":
        if req.provider == "openai":
            from app.providers.openai_provider import OpenAIProvider

            return "openai", OpenAIProvider(api_key=req.api_key)
        if req.provider == "anthropic":
            from app.providers.anthropic_provider import AnthropicProvider

            return "anthropic", AnthropicProvider(api_key=req.api_key)
        raise HTTPException(status_code=400, detail="Unknown cloud provider")
    if req.kind == "ollama":
        from app.providers.ollama_provider import OllamaProvider

        return "ollama", OllamaProvider(base_url=req.base_url or DEFAULT_OLLAMA_URL)
    # generic OpenAI-compatible endpoint
    if not req.base_url:
        raise HTTPException(status_code=400, detail="base_url is required for a custom endpoint")
    from app.providers.generic_provider import GenericOpenAIProvider

    name = req.provider or "generic"
    return name, GenericOpenAIProvider(api_key=req.api_key or "", base_url=req.base_url, provider_name=name)


@router.post("/providers/verify")
async def verify_provider(req: ProviderVerifyRequest, user=Depends(get_current_user)):  # noqa: B008
    """Verify a provider is reachable and return its available models.

    Cloud keys are validated via a health check; Ollama/generic reachability is
    confirmed by listing models from the endpoint. Never raises on a bad
    credential/URL — returns ok=False with an error so the UI can show it.
    """
    try:
        _name, provider = _build_provider(req)
    except HTTPException:
        raise

    try:
        health = await provider.health_check()
        if health.status != "healthy":
            return {"ok": False, "error": health.error or "Provider is not reachable."}
        models = await provider.list_models()
        return {
            "ok": True,
            "models": [{"id": m.id, "name": m.name} for m in models],
        }
    except Exception as exc:
        logger.info("Provider verify failed: %s", exc)
        return {"ok": False, "error": str(exc) or "Verification failed."}


@router.post("/providers/connect")
async def connect_provider(req: ProviderConnectRequest, user=Depends(get_current_user)):  # noqa: B008
    """Persist a provider config and set it as the user's default."""
    name, _provider = _build_provider(req)

    get_db().table("provider_configs").upsert(
        {
            "user_id": user.id,
            "provider": name,
            "api_key_encrypted": encrypt_secret(req.api_key or ""),
            "base_url": req.base_url or "",
            "is_default": True,
            "is_enabled": True,
        },
        on_conflict="user_id,provider",
    ).execute()

    # Local/custom models route by an explicit "{provider}/{model}" prefix; cloud
    # models (gpt-*, claude-*) route by their own name.
    default_model = ""
    if req.model:
        default_model = f"{name}/{req.model}" if req.kind in ("ollama", "generic") else req.model

    from app.routers.preferences import _get_or_create

    _get_or_create(user.id)
    patch: dict = {"default_provider": name, "updated_at": datetime.now(UTC).isoformat()}
    if default_model:
        patch["default_model"] = default_model
    get_db().table("user_preferences").update(patch).eq("user_id", user.id).execute()

    return {"ok": True, "provider": name, "default_model": default_model}


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
        "api_key_encrypted": encrypt_secret(config.api_key or ""),
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
        key = decrypt_secret(c.get("api_key_encrypted", ""))
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
