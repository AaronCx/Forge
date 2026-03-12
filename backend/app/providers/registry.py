"""Provider registry — auto-discovers configured providers and routes model strings."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.providers.base import LLMProvider, LLMResponse, ModelInfo, ProviderHealth

logger = logging.getLogger(__name__)

# Model prefix → provider mapping
MODEL_PROVIDER_MAP: dict[str, str] = {
    "gpt-": "openai",
    "o1": "openai",
    "o3": "openai",
    "claude-": "anthropic",
}


class ProviderRegistry:
    """Manages provider instances and routes model strings to the right provider."""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._default_provider: str | None = None
        self._default_model: str = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")

    @property
    def default_model(self) -> str:
        return self._default_model

    @property
    def default_provider(self) -> str | None:
        return self._default_provider

    def register(self, name: str, provider: LLMProvider, *, default: bool = False) -> None:
        """Register a provider instance."""
        self._providers[name] = provider
        if default or self._default_provider is None:
            self._default_provider = name

    def get_provider(self, name: str) -> LLMProvider | None:
        """Get a provider by name."""
        return self._providers.get(name)

    def resolve_provider(self, model: str | None = None) -> tuple[LLMProvider, str]:
        """Resolve which provider handles a model string.

        Returns (provider, model_string).
        Falls back to default provider + default model if model is None.
        """
        if model is None:
            model = self._default_model

        # Check prefix map
        for prefix, provider_name in MODEL_PROVIDER_MAP.items():
            if model.startswith(prefix):
                provider = self._providers.get(provider_name)
                if provider:
                    return provider, model

        # Check if model contains a provider hint like "ollama/llama3"
        if "/" in model:
            provider_name, _, model_id = model.partition("/")
            provider = self._providers.get(provider_name)
            if provider:
                return provider, model_id

        # Fall back to default
        if self._default_provider and self._default_provider in self._providers:
            return self._providers[self._default_provider], model

        raise ValueError(f"No provider found for model '{model}' and no default configured")

    async def complete(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        fallback: bool = True,
    ) -> LLMResponse:
        """Route a completion to the appropriate provider with optional fallback."""
        provider, resolved_model = self.resolve_provider(model)

        try:
            return await provider.complete(
                messages=messages,
                model=resolved_model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            )
        except Exception:
            if not fallback or len(self._providers) <= 1:
                raise

            # Try other providers
            failed_name = provider.provider_name
            logger.warning("Provider %s failed for model %s, trying fallback", failed_name, resolved_model)

            for name, alt_provider in self._providers.items():
                if name == failed_name:
                    continue
                try:
                    # Use the fallback provider's default model
                    fallback_model = self._default_model if name == self._default_provider else resolved_model
                    return await alt_provider.complete(
                        messages=messages,
                        model=fallback_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        tools=tools,
                    )
                except Exception:
                    continue

            raise

    async def list_all_models(self) -> list[ModelInfo]:
        """List models from all registered providers."""
        all_models: list[ModelInfo] = []
        for provider in self._providers.values():
            try:
                models = await provider.list_models()
                all_models.extend(models)
            except Exception:
                continue
        return all_models

    async def health_check_all(self) -> list[ProviderHealth]:
        """Check health of all registered providers."""
        results: list[ProviderHealth] = []
        for provider in self._providers.values():
            try:
                health = await provider.health_check()
                results.append(health)
            except Exception as e:
                results.append(
                    ProviderHealth(
                        provider=provider.provider_name,
                        status="unavailable",
                        error=str(e),
                    )
                )
        return results

    @property
    def provider_names(self) -> list[str]:
        return list(self._providers.keys())


def create_registry() -> ProviderRegistry:
    """Create and populate the provider registry from environment variables."""
    registry = ProviderRegistry()

    # OpenAI — register if API key is set
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        from app.providers.openai_provider import OpenAIProvider

        registry.register("openai", OpenAIProvider(api_key=openai_key), default=True)

    # Anthropic — register if API key is set
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key:
        from app.providers.anthropic_provider import AnthropicProvider

        registry.register("anthropic", AnthropicProvider(api_key=anthropic_key))

    # Ollama — register if OLLAMA_BASE_URL is set (or default localhost)
    ollama_url = os.getenv("OLLAMA_BASE_URL")
    if ollama_url:
        from app.providers.ollama_provider import OllamaProvider

        registry.register("ollama", OllamaProvider(base_url=ollama_url))

    # Generic OpenAI-compatible providers from GENERIC_PROVIDER_* env vars
    # Format: GENERIC_PROVIDER_NAME=base_url and GENERIC_PROVIDER_NAME_KEY=api_key
    for key, value in os.environ.items():
        if key.startswith("GENERIC_PROVIDER_") and not key.endswith("_KEY"):
            name = key.replace("GENERIC_PROVIDER_", "").lower()
            api_key = os.getenv(f"{key}_KEY", "")
            if value and api_key:
                from app.providers.generic_provider import GenericOpenAIProvider

                registry.register(name, GenericOpenAIProvider(
                    api_key=api_key,
                    base_url=value,
                    provider_name=name,
                ))

    return registry


# Global singleton
provider_registry = create_registry()
