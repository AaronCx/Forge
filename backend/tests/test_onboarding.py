"""Onboarding PR-3 — /api/onboarding/finish + tailoring helper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.services.tailoring import ABOUT_USER_MARKER, about_user_block, prepend_about


# --- tailoring helper ---------------------------------------------------------


def test_about_user_block_empty():
    assert about_user_block("") == ""
    assert about_user_block(None) == ""


def test_about_user_block_has_markers_and_text():
    block = about_user_block("I work in Rust.")
    assert ABOUT_USER_MARKER in block
    assert "I work in Rust." in block


def test_about_user_block_bounded():
    assert len(about_user_block("x" * 9000)) <= 4000 + len(ABOUT_USER_MARKER) + 20


def test_prepend_about_adds_block():
    out = prepend_about("You review code.", "Prefer terse output.")
    assert ABOUT_USER_MARKER in out
    assert out.endswith("You review code.")


def test_prepend_about_idempotent():
    once = prepend_about("You review code.", "Prefer terse output.")
    twice = prepend_about(once, "Prefer terse output.")
    assert once == twice
    assert once.count(ABOUT_USER_MARKER) == 1


def test_prepend_about_noop_without_instructions():
    assert prepend_about("You review code.", "") == "You review code."


# --- /api/onboarding/finish ---------------------------------------------------


def _wire(mock_db, *, template=None):
    """Wire a mock db: template fetch via .single(), prefs via plain select,
    inserts captured, prefs patch captured. Returns (inserts, prefs_patch)."""
    inserts: list[dict] = []
    prefs_patch: dict = {}

    def insert_side(data):
        inserts.append(data)
        return MagicMock(execute=lambda: MagicMock(data=[{**data, "id": f"new-{len(inserts)}"}]))

    mock_db.table.return_value.insert.side_effect = insert_side
    mock_db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data=template
    )
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"user_id": "test-user-id-123"}]
    )
    mock_db.table.return_value.update.side_effect = lambda p: prefs_patch.update(p) or MagicMock(
        eq=lambda *a, **k: MagicMock(execute=lambda: MagicMock(data=[{}]))
    )
    return inserts, prefs_patch


def test_finish_clones_template_with_about_block(auth_client):
    template = {
        "id": "tpl-1", "is_template": True, "name": "Code Reviewer",
        "description": "Reviews code", "system_prompt": "You review code.",
        "tools": ["data_extractor"], "workflow_steps": ["Review the code."], "model": None,
    }
    with patch("app.db._db") as mock_db:
        inserts, prefs_patch = _wire(mock_db, template=template)
        resp = auth_client.post(
            "/api/onboarding/finish",
            json={"use_case": "coding", "custom_instructions": "I work in Rust.", "template_ids": ["tpl-1"]},
        )

    assert resp.status_code == 200
    assert resp.json()["created_agents"] == 1
    seeded = inserts[0]
    assert seeded["name"] == "Code Reviewer"
    assert seeded["is_template"] is False
    assert ABOUT_USER_MARKER in seeded["system_prompt"]
    assert "I work in Rust." in seeded["system_prompt"]
    assert "You review code." in seeded["system_prompt"]
    # onboarded + prefs persisted
    assert prefs_patch["onboarded_at"]
    assert prefs_patch["use_case"] == "coding"
    assert prefs_patch["custom_instructions"] == "I work in Rust."


def test_finish_custom_agent_verbatim_without_provider(auth_client):
    with patch("app.db._db") as mock_db, \
         patch("app.providers.registry.create_user_registry", new=AsyncMock(return_value=MagicMock(provider_names=[]))):
        inserts, _ = _wire(mock_db, template=None)
        resp = auth_client.post(
            "/api/onboarding/finish",
            json={"custom_agents": [{"description": "watch my CI and summarize failures"}]},
        )

    assert resp.status_code == 200
    assert resp.json()["created_agents"] == 1
    agent = inserts[0]
    # Name derived from the description; prompt uses the verbatim text.
    assert agent["name"]
    assert "watch my CI and summarize failures" in agent["system_prompt"]


def test_finish_skips_non_template_ids(auth_client):
    not_a_template = {"id": "x", "is_template": False, "name": "Someone's agent"}
    with patch("app.db._db") as mock_db:
        inserts, prefs_patch = _wire(mock_db, template=not_a_template)
        resp = auth_client.post("/api/onboarding/finish", json={"template_ids": ["x"]})

    assert resp.status_code == 200
    assert resp.json()["created_agents"] == 0
    assert inserts == []
    # Still marks the user onboarded.
    assert prefs_patch["onboarded_at"]
