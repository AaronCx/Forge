"""Provider registry — auto-discovers configured providers and routes model strings."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.providers.base import LLMProvider, LLMResponse, ModelInfo, ProviderHealth

if TYPE_CHECKING:
    from app.kernel.types import KMessage, StreamEvent, ToolSpec, TurnResult

logger = logging.getLogger(__name__)


@dataclass
class FallbackPolicy:
    """Controls cross-provider retry for kernel turns (default: no fallback).

    Client (4xx) errors are never retried when ``exclude_client_errors`` is set —
    a bad request will fail identically everywhere.
    """

    enabled: bool = False
    same_capabilities_only: bool = False
    exclude_client_errors: bool = True


def _is_client_error(exc: Exception) -> bool:
    """True for a 4xx-class error from any provider SDK or httpx."""
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    return isinstance(status, int) and 400 <= status < 500


def load_user_fallback_policy(user_id: str | None) -> FallbackPolicy:
    """Load a user's stored FallbackPolicy (harness-plan.md Phase 7; default off)."""
    if not user_id:
        return FallbackPolicy()
    try:
        from app.db import get_db

        result = (
            get_db().table("user_preferences").select("fallback_policy_json")
            .eq("user_id", user_id).execute()
        )
        rows = result.data if isinstance(result.data, list) else []
        raw = rows[0].get("fallback_policy_json") if rows else None
        if isinstance(raw, dict):
            return FallbackPolicy(
                enabled=bool(raw.get("enabled", False)),
                same_capabilities_only=bool(raw.get("same_capabilities_only", False)),
                exclude_client_errors=bool(raw.get("exclude_client_errors", True)),
            )
    except Exception:  # noqa: BLE001 - default to the safe (no-fallback) policy
        logger.debug("fallback policy read failed for %s", user_id)
    return FallbackPolicy()

# Model prefix → provider mapping.
# TODO(phase-8): remove in favor of ModelCard.provider lookups from
# app/kernel/models.json. Kept as the last-resort routing fallback until then.
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

        # ModelCard-first routing (harness-plan.md Phase 2): prefer the provider
        # declared in models.json when it is actually registered here. Falls
        # through to the legacy prefix/explicit/default logic otherwise.
        from app.kernel.models import get_model_card

        card = get_model_card(model)
        if card is not None:
            card_provider = self._providers.get(card.provider)
            if card_provider:
                return card_provider, model

        # Check if a registered provider claims this prefix (e.g. "gpt-" → openai).
        # Only treat the prefix as routable when that provider is actually
        # registered — otherwise fall through to the default provider with
        # a sensible model swap.
        for prefix, provider_name in MODEL_PROVIDER_MAP.items():
            if model.startswith(prefix):
                provider = self._providers.get(provider_name)
                if provider:
                    return provider, model
                # Prefix matches a known provider that isn't registered here.
                # Don't return; let the default-provider fallback below pick a
                # model that actually exists on the registered provider.
                model_unrouteable_via_prefix = True
                break
        else:
            model_unrouteable_via_prefix = False

        # Explicit provider hint, e.g. "ollama/llama3.2:3b"
        if "/" in model:
            provider_name, _, model_id = model.partition("/")
            provider = self._providers.get(provider_name)
            if provider:
                return provider, model_id

        # Fall back to the default provider. If the seeded default model is
        # for an unregistered provider (the common Mac-mini-with-only-Ollama
        # case where DEFAULT_MODEL=gpt-4o-mini doesn't route), drop the
        # unrouteable model and let the provider use its own default — passing
        # an empty string here makes provider.complete() fall back to whatever
        # it considers its default, rather than 404'ing on `gpt-4o-mini`.
        if self._default_provider and self._default_provider in self._providers:
            provider = self._providers[self._default_provider]
            if model_unrouteable_via_prefix:
                return provider, getattr(provider, "default_model", "") or ""
            return provider, model

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

    # --- kernel interface (harness-plan.md Phase 2) ---

    async def turn(
        self,
        messages: list[KMessage],
        model: str | None = None,
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        policy: FallbackPolicy | None = None,
    ) -> TurnResult:
        """Route a kernel turn to the resolved provider, with optional fallback."""
        from typing import cast

        provider, resolved_model = self.resolve_provider(model)
        policy = policy or FallbackPolicy()

        try:
            return cast(
                "TurnResult",
                await provider.turn(
                    messages, resolved_model, tools=tools,
                    temperature=temperature, max_tokens=max_tokens,
                ),
            )
        except Exception as exc:
            if not policy.enabled or len(self._providers) <= 1:
                raise
            if policy.exclude_client_errors and _is_client_error(exc):
                raise  # a 4xx fails identically everywhere — do not retry

            failed_name = provider.provider_name
            logger.warning(
                "Provider %s turn failed for %s, trying fallback", failed_name, resolved_model
            )
            for name, alt in self._providers.items():
                if name == failed_name:
                    continue
                try:
                    alt_model = self._default_model if name == self._default_provider else resolved_model
                    result = cast(
                        "TurnResult",
                        await alt.turn(
                            messages, alt_model, tools=tools,
                            temperature=temperature, max_tokens=max_tokens,
                        ),
                    )
                    logger.warning("Fallback turn succeeded on provider %s", name)
                    return result
                except Exception:
                    continue
            raise

    async def stream(
        self,
        messages: list[KMessage],
        model: str | None = None,
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        """Stream a kernel turn from the resolved provider.

        Mid-stream cross-provider fallback is intentionally not attempted (events
        already emitted cannot be retracted); use ``turn`` for fallback.
        """
        provider, resolved_model = self.resolve_provider(model)
        async for ev in provider.stream_turn(
            messages, resolved_model, tools=tools,
            temperature=temperature, max_tokens=max_tokens,
        ):
            yield ev

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

    # Google (Gemini) — register if API key is set
    google_key = os.getenv("GOOGLE_API_KEY")
    if google_key:
        from app.providers.google_provider import GoogleProvider

        registry.register("google", GoogleProvider(api_key=google_key))

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


async def create_user_registry(user_id: str) -> ProviderRegistry:
    """Create a provider registry from a user's stored provider_configs.

    Falls back to the global env-var-based registry if the user has no configs.
    """
    from app.db import get_db

    result = (
        get_db().table("provider_configs")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_enabled", True)
        .execute()
    )
    configs = result.data or []

    registry = ProviderRegistry()

    from app.services.security.secrets import decrypt_secret

    for config in configs:
        provider_name = config["provider"]
        api_key = decrypt_secret(config.get("api_key_encrypted", ""))
        base_url = config.get("base_url", "") or None
        is_default = config.get("is_default", False)

        try:
            if provider_name == "openai":
                from app.providers.openai_provider import OpenAIProvider

                registry.register("openai", OpenAIProvider(api_key=api_key, base_url=base_url), default=is_default)
            elif provider_name == "anthropic":
                from app.providers.anthropic_provider import AnthropicProvider

                registry.register("anthropic", AnthropicProvider(api_key=api_key), default=is_default)
            elif provider_name == "google":
                from app.providers.google_provider import GoogleProvider

                registry.register("google", GoogleProvider(api_key=api_key, base_url=base_url), default=is_default)
            elif provider_name == "ollama":
                from app.providers.ollama_provider import OllamaProvider

                registry.register("ollama", OllamaProvider(base_url=base_url or "http://localhost:11434"), default=is_default)
            else:
                # Generic OpenAI-compatible provider
                from app.providers.generic_provider import GenericOpenAIProvider

                registry.register(provider_name, GenericOpenAIProvider(
                    api_key=api_key, base_url=base_url or "", provider_name=provider_name,
                ), default=is_default)
        except Exception:
            logger.warning("Failed to create provider %s for user %s", provider_name, user_id)
            continue

    # Fall back to global registry if user has no configs
    if not registry.provider_names:
        return provider_registry

    return registry


# Global singleton
provider_registry = create_registry()
