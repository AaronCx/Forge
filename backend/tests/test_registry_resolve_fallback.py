"""Regression test for QA Finding #31 — registry falls back to a routable model.

Without this, agents created without an explicit `model` field 404 against
Ollama because the registry's seeded default (`gpt-4o-mini`) doesn't exist on
the registered provider.
"""

from __future__ import annotations

from app.providers.registry import ProviderRegistry


class _FakeOllama:
    provider_name = "ollama"
    default_model = "qwen2.5:7b-instruct"


def test_unrouteable_prefix_falls_back_to_provider_default():
    """gpt-4o-mini → no openai registered → use ollama's own default model."""
    reg = ProviderRegistry()
    reg.register("ollama", _FakeOllama(), default=True)
    reg._default_model = "gpt-4o-mini"  # the registry's hard-coded seed

    provider, model = reg.resolve_provider(None)
    assert provider.provider_name == "ollama"
    # Critical: must not return "gpt-4o-mini" — Ollama would 404.
    assert model == "qwen2.5:7b-instruct"


def test_explicit_provider_prefix_wins_over_fallback():
    """ollama/llama3.2:3b should route to ollama with the bare model id."""
    reg = ProviderRegistry()
    reg.register("ollama", _FakeOllama(), default=True)

    provider, model = reg.resolve_provider("ollama/llama3.2:3b")
    assert provider.provider_name == "ollama"
    assert model == "llama3.2:3b"
