"""Onboarding PR-2 — provider verify/connect (cloud + ollama + generic)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


def _fake_provider(*, healthy=True, models=("gpt-4o", "gpt-4o-mini")):
    p = MagicMock()
    p.health_check = AsyncMock(
        return_value=SimpleNamespace(status="healthy" if healthy else "unavailable", error=None if healthy else "bad key")
    )
    p.list_models = AsyncMock(return_value=[SimpleNamespace(id=m, name=m) for m in models])
    return p


def test_verify_cloud_openai_returns_models(auth_client):
    fake = _fake_provider()
    with patch("app.providers.openai_provider.OpenAIProvider", return_value=fake):
        resp = auth_client.post("/api/providers/verify", json={"kind": "cloud", "provider": "openai", "api_key": "sk-x"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert {m["id"] for m in body["models"]} == {"gpt-4o", "gpt-4o-mini"}


def test_verify_ollama_no_key(auth_client):
    fake = _fake_provider(models=("llama3.2:3b", "qwen2.5:7b-instruct"))
    with patch("app.providers.ollama_provider.OllamaProvider", return_value=fake):
        resp = auth_client.post("/api/providers/verify", json={"kind": "ollama"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert any("llama" in m["id"] for m in body["models"])


def test_verify_generic_requires_base_url(auth_client):
    resp = auth_client.post("/api/providers/verify", json={"kind": "generic"})
    assert resp.status_code == 400


def test_verify_bad_key_returns_ok_false(auth_client):
    fake = _fake_provider(healthy=False)
    with patch("app.providers.openai_provider.OpenAIProvider", return_value=fake):
        resp = auth_client.post("/api/providers/verify", json={"kind": "cloud", "provider": "openai", "api_key": "bad"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]


def test_connect_ollama_sets_prefixed_default_model(auth_client):
    captured = {}
    with patch("app.db._db") as mock_db, \
         patch("app.providers.ollama_provider.OllamaProvider", return_value=_fake_provider()):
        # preferences _get_or_create read
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "test-user-id-123"}]
        )
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{"id": "c1"}])
        mock_db.table.return_value.update.side_effect = lambda p: captured.update(p) or MagicMock(
            eq=lambda *a, **k: MagicMock(execute=lambda: MagicMock(data=[{}]))
        )

        # auth: override is via get_current_user dependency (auth_client), but the
        # endpoint also reads/writes through app.db._db which we patch here.
        resp = auth_client.post(
            "/api/providers/connect",
            json={"kind": "ollama", "model": "qwen2.5:7b-instruct"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "ollama"
    assert body["default_model"] == "ollama/qwen2.5:7b-instruct"
    assert captured["default_provider"] == "ollama"


def test_connect_cloud_keeps_plain_model_name(auth_client):
    captured = {}
    with patch("app.db._db") as mock_db, \
         patch("app.providers.openai_provider.OpenAIProvider", return_value=_fake_provider()):
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "test-user-id-123"}]
        )
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{"id": "c1"}])
        mock_db.table.return_value.update.side_effect = lambda p: captured.update(p) or MagicMock(
            eq=lambda *a, **k: MagicMock(execute=lambda: MagicMock(data=[{}]))
        )
        resp = auth_client.post(
            "/api/providers/connect",
            json={"kind": "cloud", "provider": "openai", "api_key": "sk-x", "model": "gpt-4o-mini"},
        )

    assert resp.status_code == 200
    assert resp.json()["default_model"] == "gpt-4o-mini"
