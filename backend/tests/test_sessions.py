"""Phase 6 — durable sessions and the chat surface.

Round-trip persistence, resume mid-thread, mid-session model switch, compaction
that preserves originals, fork, and the SSE turn driver over a fake registry.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

import app.db as dbmod
from app.db.sqlite_backend import SQLiteBackend
from app.kernel.types import (
    KMessage,
    TextBlock,
    TextDelta,
    TurnDone,
    TurnResult,
    Usage,
)
from app.services import sessions as svc


@pytest.fixture
def db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    backend = SQLiteBackend(path)
    asyncio.new_event_loop().run_until_complete(backend.initialize())
    monkeypatch.setattr(dbmod, "_db", backend)
    yield backend
    os.remove(path)


class _FakeRegistry:
    def __init__(self, text="Assistant reply.", provider="openai"):
        self._text = text
        self._provider = provider

    async def stream(self, messages, model, *, tools=None):
        yield TextDelta(text=self._text)
        yield TurnDone(turn=TurnResult(
            blocks=[TextBlock(self._text)], stop_reason="end",
            usage=Usage(input_tokens=5, output_tokens=7),
            model=model or "gpt-4o-mini", provider=self._provider,
        ))

    async def turn(self, messages, model=None, *, tools=None, temperature=0.7,
                   max_tokens=4096, policy=None):
        return TurnResult(
            blocks=[TextBlock("SUMMARY: earlier conversation")], stop_reason="end",
            usage=Usage(input_tokens=3, output_tokens=4),
            model=model or "gpt-4o-mini", provider=self._provider,
        )


def test_schema_comments_have_no_semicolons():
    # initialize() splits SCHEMA on ';', so a ';' inside a '--' comment truncates
    # the statement. Guard against reintroducing that class of bug.
    from app.db.sqlite_schema import SCHEMA

    offenders = [
        line for line in SCHEMA.splitlines()
        if line.lstrip().startswith("--") and ";" in line
    ]
    assert not offenders, f"semicolon inside SQL comment(s): {offenders}"


def test_create_get_list_and_ownership(db):
    s = svc.create_session("u1", title="Chat", model="gpt-4o-mini")
    assert s["title"] == "Chat"
    assert svc.get_session(s["id"], "u1")["id"] == s["id"]
    assert svc.get_session(s["id"], "someone-else") is None  # tenant boundary
    assert len(svc.list_sessions("u1")) == 1


@pytest.mark.asyncio
async def test_turn_persists_and_resumes(db):
    s = svc.create_session("u1", model="gpt-4o-mini", system_prompt="Be helpful.")
    fake = _FakeRegistry(text="Hello back.")
    with patch("app.providers.registry.create_user_registry", AsyncMock(return_value=fake)):
        events = [e async for e in svc.run_turn(s["id"], "u1", "Hi there")]

    assert events[-1]["type"] == "done"
    assert any(e["type"] == "token" for e in events)

    # Resume: the event log holds the user + assistant messages.
    msgs = svc.build_messages(svc.get_session(s["id"], "u1"))
    roles = [m.role for m in msgs]
    assert roles[0] == "system"
    assert "user" in roles and "assistant" in roles
    assert msgs[-1].blocks[0].text == "Hello back."


@pytest.mark.asyncio
async def test_mid_session_model_switch(db):
    s = svc.create_session("u1", model="gpt-4o-mini")
    fake = _FakeRegistry()
    with patch("app.providers.registry.create_user_registry", AsyncMock(return_value=fake)):
        _ = [e async for e in svc.run_turn(s["id"], "u1", "hi",
                                            model_override="claude-sonnet-4-20250514")]
    assert svc.get_session(s["id"], "u1")["model"] == "claude-sonnet-4-20250514"


@pytest.mark.asyncio
async def test_compaction_preserves_originals(db):
    s = svc.create_session("u1", model="gpt-4o-mini")
    # Seed more than keep_last message events.
    for i in range(12):
        svc.append_event(s["id"], "message",
                         {"role": "user", "blocks": [{"kind": "text", "text": f"msg {i}"}]})
    before = len([e for e in svc.get_events(s["id"]) if e["kind"] == "message"])

    fake = _FakeRegistry()
    with patch("app.providers.registry.create_user_registry", AsyncMock(return_value=fake)):
        did = await svc.compact_session(s["id"], "u1", keep_last=4, force=True)
    assert did is True

    events = svc.get_events(s["id"])
    # originals are still present (reversible) ...
    assert len([e for e in events if e["kind"] == "message"]) == before
    # ... and a compaction event was recorded.
    compactions = [e for e in events if e["kind"] == "compaction"]
    assert len(compactions) == 1
    assert "SUMMARY" in compactions[0]["payload_json"]["summary"]

    # build_messages now pins the summary and drops the replaced tail.
    msgs = svc.build_messages(svc.get_session(s["id"], "u1"))
    assert any("Summary of earlier conversation" in b.text
               for m in msgs if m.role == "system" for b in m.blocks)
    assert sum(1 for m in msgs if m.role == "user") == 4  # only the kept tail


@pytest.mark.asyncio
async def test_fork_copies_the_log(db):
    s = svc.create_session("u1", model="gpt-4o-mini")
    svc.append_event(s["id"], "message",
                     {"role": "user", "blocks": [{"kind": "text", "text": "original"}]})
    child = svc.fork_session(s["id"], "u1")
    assert child["id"] != s["id"]
    child_events = svc.get_events(child["id"])
    assert any(e["payload_json"].get("blocks", [{}])[0].get("text") == "original"
               for e in child_events)


def test_workspace_agents_md_injected(db, tmp_path):
    (tmp_path / "AGENTS.md").write_text("Follow the house style.")
    s = svc.create_session("u1", model="gpt-4o-mini", workspace_root=str(tmp_path))
    msgs = svc.build_messages(svc.get_session(s["id"], "u1"))
    system = next(m for m in msgs if m.role == "system")
    assert "Follow the house style." in system.blocks[0].text


def test_router_gated_by_flag_and_crud(db, auth_client, monkeypatch):
    # Flag off → 404 (sessions default on now, so disable explicitly).
    monkeypatch.setenv("FORGE_SESSIONS", "0")
    assert auth_client.post("/api/sessions", json={"title": "x"}).status_code == 404

    # Flag on → full CRUD.
    monkeypatch.setenv("FORGE_SESSIONS", "1")
    created = auth_client.post(
        "/api/sessions", json={"title": "Chat", "model": "gpt-4o-mini"}
    ).json()
    sid = created["id"]
    assert auth_client.get("/api/sessions").json()[0]["id"] == sid
    assert auth_client.get(f"/api/sessions/{sid}").json()["session"]["id"] == sid
    # mid-session model switch
    switched = auth_client.patch(
        f"/api/sessions/{sid}", json={"model": "claude-sonnet-4-20250514"}
    ).json()
    assert switched["model"] == "claude-sonnet-4-20250514"
    # fork + delete
    fork = auth_client.post(f"/api/sessions/{sid}/fork").json()
    assert fork["id"] != sid
    assert auth_client.delete(f"/api/sessions/{sid}").status_code == 204


@pytest.mark.asyncio
async def test_approved_pending_tool_auto_retries_on_next_message(db):
    """Audit M3: a tool call parked on APPROVAL_PENDING is re-executed
    automatically once its approval flips to approved — the model never has to
    choose to retry."""
    from app.kernel.toolplane import approval_key
    from app.kernel.types import ToolSpec, ToolUseBlock

    s = svc.create_session("u1", model="gpt-4o-mini")
    # Seed history: assistant requested cu.drive_run, the plane parked it.
    svc.append_event(s["id"], "message", {"role": "assistant", "blocks": [
        {"kind": "tool_use", "id": "tc1", "name": "cu.drive_run",
         "input": {"command": "echo hi"}}]})
    svc.append_event(s["id"], "message", {"role": "tool", "blocks": [
        {"kind": "tool_result", "tool_use_id": "tc1",
         "output": "APPROVAL_PENDING: 'cu.drive_run' is awaiting human approval.",
         "is_error": False}]})
    # The approval row the plane filed, now approved by a human.
    tu = ToolUseBlock(id="tc1", name="cu.drive_run", input={"command": "echo hi"})
    spec = ToolSpec(name="cu.drive_run", description="", danger_level="dangerous")
    db.table("approvals").insert({
        "id": "ap1", "user_id": "u1", "blueprint_run_id": s["id"],
        "node_id": approval_key(spec, tu, "tool"), "status": "approved",
    }).execute()

    fake = _FakeRegistry()
    drive_result = {"success": True, "output": "hi", "exit_code": 0}
    with (
        patch("app.providers.registry.create_user_registry", AsyncMock(return_value=fake)),
        patch("app.services.computer_use.drive.nodes.execute",
              AsyncMock(return_value=drive_result)),
    ):
        events = [e async for e in svc.run_turn(s["id"], "u1", "continue")]

    retried = [e for e in events
               if e["type"] == "tool_result" and e.get("data", {}).get("retried")]
    assert len(retried) == 1
    assert retried[0]["data"]["tool"] == "cu.drive_run"
    assert not retried[0]["data"]["is_error"]

    # The outcome is persisted in the log ahead of the new user message.
    log = svc.build_messages(svc.get_session(s["id"], "u1"))
    notes = [b.text for m in log for b in m.blocks
             if isinstance(b, TextBlock) and b.text.startswith("[approved tool call")]
    assert len(notes) == 1 and "tc1" in notes[0]

    # A second turn does not retry again (the note supersedes the pending result).
    with patch("app.providers.registry.create_user_registry", AsyncMock(return_value=fake)):
        events2 = [e async for e in svc.run_turn(s["id"], "u1", "and again")]
    assert not [e for e in events2
                if e["type"] == "tool_result" and e.get("data", {}).get("retried")]


@pytest.mark.asyncio
async def test_still_pending_tool_is_not_retried(db):
    s = svc.create_session("u1", model="gpt-4o-mini")
    svc.append_event(s["id"], "message", {"role": "assistant", "blocks": [
        {"kind": "tool_use", "id": "tc1", "name": "cu.drive_run",
         "input": {"command": "echo hi"}}]})
    svc.append_event(s["id"], "message", {"role": "tool", "blocks": [
        {"kind": "tool_result", "tool_use_id": "tc1",
         "output": "APPROVAL_PENDING: awaiting approval", "is_error": False}]})
    fake = _FakeRegistry()
    with patch("app.providers.registry.create_user_registry", AsyncMock(return_value=fake)):
        events = [e async for e in svc.run_turn(s["id"], "u1", "anything new?")]
    assert not [e for e in events
                if e["type"] == "tool_result" and e.get("data", {}).get("retried")]


@pytest.mark.asyncio
async def test_message_serialization_round_trip():
    from app.kernel.serialize import message_from_dict, message_to_dict
    from app.kernel.types import ToolResultBlock, ToolUseBlock

    original = KMessage(role="assistant", blocks=[
        TextBlock("hi"),
        ToolUseBlock(id="c1", name="node.x", input={"a": 1}),
    ])
    assert message_from_dict(message_to_dict(original)) == original
    tool_msg = KMessage(role="tool", blocks=[ToolResultBlock(tool_use_id="c1", output="ok")])
    assert message_from_dict(message_to_dict(tool_msg)) == tool_msg
