"""Tests for the multi-model provider system."""


import pytest

from app.providers.base import (
    LLMProvider,
    LLMResponse,
    ModelInfo,
    ProviderHealth,
    StreamChunk,
)
from app.providers.registry import ProviderRegistry

# --- Base interface tests ---


def test_llm_response_fields():
    resp = LLMResponse(
        content="Hello",
        model="gpt-4o-mini",
        input_tokens=10,
        output_tokens=5,
        finish_reason="stop",
        latency_ms=100.0,
        provider="openai",
    )
    assert resp.content == "Hello"
    assert resp.model == "gpt-4o-mini"
    assert resp.input_tokens == 10
    assert resp.output_tokens == 5
    assert resp.provider == "openai"


def test_model_info_defaults():
    info = ModelInfo(id="test", name="test", provider="openai")
    assert info.supports_tools is True
    assert info.supports_streaming is True
    assert info.context_window is None


def test_provider_health_status():
    h = ProviderHealth(provider="openai", status="healthy", latency_ms=50.0)
    assert h.provider == "openai"
    assert h.status == "healthy"


def test_stream_chunk_defaults():
    chunk = StreamChunk()
    assert chunk.content == ""
    assert chunk.finish_reason is None


# --- Registry tests ---


class MockProvider(LLMProvider):
    """Minimal provider for testing registry."""

    provider_name = "mock"

    async def complete(self, messages, model, **kwargs):
        return LLMResponse(
            content="mock response",
            model=model,
            input_tokens=5,
            output_tokens=10,
            finish_reason="stop",
            latency_ms=10,
            provider=self.provider_name,
        )

    async def stream_complete(self, messages, model, **kwargs):
        yield StreamChunk(content="chunk", model=model, provider=self.provider_name)

    async def count_tokens(self, text, model):
        return len(text) // 4

    async def list_models(self):
        return [ModelInfo(id="mock-model", name="Mock Model", provider=self.provider_name)]

    async def health_check(self):
        return ProviderHealth(provider=self.provider_name, status="healthy", latency_ms=1.0)


def test_registry_register_and_get():
    registry = ProviderRegistry()
    provider = MockProvider()
    registry.register("mock", provider)
    assert registry.get_provider("mock") is provider
    assert registry.get_provider("nonexistent") is None


def test_registry_default_provider():
    registry = ProviderRegistry()
    p1 = MockProvider()
    p1.provider_name = "first"
    p2 = MockProvider()
    p2.provider_name = "second"

    registry.register("first", p1)
    registry.register("second", p2, default=True)
    assert registry.default_provider == "second"


def test_registry_resolve_by_prefix():
    registry = ProviderRegistry()
    openai_provider = MockProvider()
    openai_provider.provider_name = "openai"
    registry.register("openai", openai_provider)

    provider, model = registry.resolve_provider("gpt-4o")
    assert provider is openai_provider
    assert model == "gpt-4o"


def test_registry_resolve_slash_syntax():
    registry = ProviderRegistry()
    ollama_provider = MockProvider()
    ollama_provider.provider_name = "ollama"
    registry.register("ollama", ollama_provider)

    provider, model = registry.resolve_provider("ollama/llama3")
    assert provider is ollama_provider
    assert model == "llama3"


def test_registry_resolve_default():
    registry = ProviderRegistry()
    provider = MockProvider()
    registry.register("mock", provider, default=True)

    result_provider, model = registry.resolve_provider(None)
    assert result_provider is provider


def test_registry_no_provider_raises():
    registry = ProviderRegistry()
    with pytest.raises(ValueError, match="No provider found"):
        registry.resolve_provider("unknown-model")


def test_registry_provider_names():
    registry = ProviderRegistry()
    registry.register("a", MockProvider())
    registry.register("b", MockProvider())
    assert set(registry.provider_names) == {"a", "b"}


@pytest.mark.asyncio
async def test_registry_complete():
    registry = ProviderRegistry()
    registry.register("mock", MockProvider(), default=True)

    response = await registry.complete(
        messages=[{"role": "user", "content": "hello"}],
    )
    assert response.content == "mock response"
    assert response.provider == "mock"


@pytest.mark.asyncio
async def test_registry_list_all_models():
    registry = ProviderRegistry()
    registry.register("mock", MockProvider())

    models = await registry.list_all_models()
    assert len(models) == 1
    assert models[0].id == "mock-model"


@pytest.mark.asyncio
async def test_registry_health_check_all():
    registry = ProviderRegistry()
    registry.register("mock", MockProvider())

    results = await registry.health_check_all()
    assert len(results) == 1
    assert results[0].status == "healthy"


# --- Routing tests ---


def test_anthropic_prefix_routing():
    registry = ProviderRegistry()
    anthropic_provider = MockProvider()
    anthropic_provider.provider_name = "anthropic"
    registry.register("anthropic", anthropic_provider)

    provider, model = registry.resolve_provider("claude-sonnet-4-20250514")
    assert provider is anthropic_provider
    assert model == "claude-sonnet-4-20250514"


def test_openai_o_model_routing():
    registry = ProviderRegistry()
    openai_provider = MockProvider()
    openai_provider.provider_name = "openai"
    registry.register("openai", openai_provider)

    for model_str in ["o1", "o1-mini", "o3-mini"]:
        provider, model = registry.resolve_provider(model_str)
        assert provider is openai_provider
        assert model == model_str


# --- Fallback tests ---


class FailingProvider(LLMProvider):
    provider_name = "failing"

    async def complete(self, messages, model, **kwargs):
        raise ConnectionError("Provider down")

    async def stream_complete(self, messages, model, **kwargs):
        raise ConnectionError("Provider down")
        yield  # type: ignore[misc]

    async def count_tokens(self, text, model):
        return 0

    async def list_models(self):
        return []

    async def health_check(self):
        return ProviderHealth(provider=self.provider_name, status="unavailable", error="down")


@pytest.mark.asyncio
async def test_registry_fallback():
    registry = ProviderRegistry()
    registry.register("failing", FailingProvider(), default=True)
    registry.register("mock", MockProvider())

    # Should fall back to mock when failing provider errors
    response = await registry.complete(
        messages=[{"role": "user", "content": "test"}],
        fallback=True,
    )
    assert response.content == "mock response"


@pytest.mark.asyncio
async def test_registry_no_fallback():
    registry = ProviderRegistry()
    registry.register("failing", FailingProvider(), default=True)

    with pytest.raises(ConnectionError):
        await registry.complete(
            messages=[{"role": "user", "content": "test"}],
            fallback=False,
        )


# --- Token tracker cost tests ---


def test_cost_calculation():
    from app.services.token_tracker import calculate_cost

    cost = calculate_cost("gpt-4o-mini", 1000, 500)
    expected = (1000 / 1_000_000) * 0.15 + (500 / 1_000_000) * 0.60
    assert abs(cost - round(expected, 6)) < 0.000001


def test_cost_anthropic():
    from app.services.token_tracker import calculate_cost

    cost = calculate_cost("claude-sonnet-4-20250514", 1000, 500)
    expected = (1000 / 1_000_000) * 3.00 + (500 / 1_000_000) * 15.00
    assert abs(cost - round(expected, 6)) < 0.000001


def test_cost_unknown_model():
    from app.services.token_tracker import calculate_cost

    cost = calculate_cost("unknown-model", 1000, 500)
    # Should use default pricing
    assert cost > 0


def test_cost_ollama_free():
    from app.services.token_tracker import calculate_cost

    cost = calculate_cost("ollama/llama3", 10000, 5000)
    assert cost == 0.0


# --- Backward compatibility tests ---


def test_default_model_env():
    """Registry should read DEFAULT_MODEL from env."""
    import os
    old_val = os.environ.get("DEFAULT_MODEL")
    os.environ["DEFAULT_MODEL"] = "gpt-4o"
    try:
        registry = ProviderRegistry()
        assert registry.default_model == "gpt-4o"
    finally:
        if old_val is None:
            os.environ.pop("DEFAULT_MODEL", None)
        else:
            os.environ["DEFAULT_MODEL"] = old_val


# --- API endpoint tests ---


def test_providers_list(auth_client):
    response = auth_client.get(
        "/api/providers", headers={"Authorization": "Bearer test-token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    assert "default_model" in data


def test_providers_health(auth_client):
    response = auth_client.get(
        "/api/providers/health", headers={"Authorization": "Bearer test-token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_providers_models(auth_client):
    response = auth_client.get(
        "/api/providers/models", headers={"Authorization": "Bearer test-token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
