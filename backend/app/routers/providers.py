"""Provider API routes — model listing, health, and configuration."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.providers.registry import provider_registry
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


# --- Model listing ---


@router.get("/providers/models", response_model=list[ModelResponse])
async def list_all_models(
    _user=Depends(get_current_user),  # noqa: B008
):
    """List all available models across all configured providers."""
    models = await provider_registry.list_all_models()
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
    _user=Depends(get_current_user),  # noqa: B008
):
    """List models for a specific provider."""
    p = provider_registry.get_provider(provider)
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
    _user=Depends(get_current_user),  # noqa: B008
):
    """Check health of all configured providers."""
    results = await provider_registry.health_check_all()
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
    _user=Depends(get_current_user),  # noqa: B008
):
    """List configured providers and the default model."""
    return {
        "providers": provider_registry.provider_names,
        "default_model": provider_registry.default_model,
        "default_provider": provider_registry.default_provider,
    }
