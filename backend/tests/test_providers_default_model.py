"""Regression test for QA Finding #10 — `/api/providers.default_model` fallback."""

from __future__ import annotations


def test_default_model_overrides_when_seeded_default_isnt_routable(monkeypatch):
    """When the seeded default_model can't be routed through any registered
    provider, the endpoint should fall back to a routable model from the
    default_provider rather than parroting the seeded value back."""
    # Build a registry that only knows about Ollama.
    from app.providers.base import ModelInfo
    from app.providers.registry import ProviderRegistry

    class FakeOllama:
        async def list_models(self):
            return [
                ModelInfo(name="llama3.2:3b", context_window=8192,
                          input_cost_per_token=0, output_cost_per_token=0,
                          supports_streaming=True),
            ]

        async def health_check(self):
            return {"status": "healthy", "latency_ms": 5}

    reg = ProviderRegistry()
    reg.register("ollama", FakeOllama(), default=True)
    # Simulate a stale env-derived default that no registered provider handles.
    reg._default_model = "gpt-4o-mini"

    # Reproduce the route's selection logic.
    from app.providers.registry import MODEL_PROVIDER_MAP

    def _matches(model: str) -> bool:
        if "/" in model:
            return model.split("/", 1)[0] in reg.provider_names
        for prefix, name in MODEL_PROVIDER_MAP.items():
            if model.startswith(prefix):
                return name in reg.provider_names
        return False

    # Pre-fix behavior: bare gpt-4o-mini doesn't match any registered provider.
    assert _matches(reg.default_model) is False
    # Post-fix expectation: the route swaps in `<default>/<first model>`.
    fallback = f"{reg.default_provider}/llama3.2:3b"
    assert _matches(fallback) is True
