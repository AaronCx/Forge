"""Onboarding PR-1 — preferences schema + /api/preferences."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.db.sqlite_schema import COLUMN_MIGRATIONS


def test_migration_covers_onboarding_columns():
    cols = {(t, c) for t, c, _ in COLUMN_MIGRATIONS}
    assert ("user_preferences", "onboarded_at") in cols
    assert ("user_preferences", "use_case") in cols
    assert ("user_preferences", "custom_instructions") in cols


def test_get_preferences_autocreates_row(auth_client):
    created_row = {
        "user_id": "test-user-id-123",
        "default_model": "gpt-4o-mini",
        "default_provider": "openai",
        "onboarded_at": None,
        "use_case": None,
        "custom_instructions": None,
    }
    with patch("app.db._db") as mock_db:
        # First select → empty; insert → the new row.
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[created_row])

        resp = auth_client.get("/api/preferences")

    assert resp.status_code == 200
    body = resp.json()
    assert body["onboarded_at"] is None
    assert body["default_model"] == "gpt-4o-mini"


def test_get_preferences_returns_existing(auth_client):
    row = {
        "user_id": "test-user-id-123",
        "default_model": "ollama/qwen2.5:7b-instruct",
        "default_provider": "ollama",
        "onboarded_at": "2026-06-02T00:00:00Z",
        "use_case": "coding",
        "custom_instructions": "I work in Rust.",
    }
    with patch("app.db._db") as mock_db:
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[row])
        resp = auth_client.get("/api/preferences")

    assert resp.status_code == 200
    assert resp.json()["use_case"] == "coding"


def test_put_preferences_patches_fields(auth_client):
    captured = {}

    with patch("app.db._db") as mock_db:
        existing = {"user_id": "test-user-id-123", "default_model": "gpt-4o-mini", "default_provider": "openai",
                    "onboarded_at": None, "use_case": None, "custom_instructions": None}
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[existing])

        def capture_update(patch_dict):
            captured.update(patch_dict)
            return MagicMock(eq=lambda *a, **k: MagicMock(execute=lambda: MagicMock(data=[existing])))

        mock_db.table.return_value.update.side_effect = capture_update

        resp = auth_client.put("/api/preferences", json={"use_case": "research", "custom_instructions": "Be terse."})

    assert resp.status_code == 200
    assert captured["use_case"] == "research"
    assert captured["custom_instructions"] == "Be terse."
    assert "updated_at" in captured


def test_put_preferences_bounds_custom_instructions(auth_client):
    captured = {}
    with patch("app.db._db") as mock_db:
        existing = {"user_id": "test-user-id-123", "default_model": "gpt-4o-mini", "default_provider": "openai",
                    "onboarded_at": None, "use_case": None, "custom_instructions": None}
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[existing])
        mock_db.table.return_value.update.side_effect = lambda p: captured.update(p) or MagicMock(
            eq=lambda *a, **k: MagicMock(execute=lambda: MagicMock(data=[existing]))
        )
        resp = auth_client.put("/api/preferences", json={"custom_instructions": "x" * 10000})

    assert resp.status_code == 200
    assert len(captured["custom_instructions"]) == 4000
