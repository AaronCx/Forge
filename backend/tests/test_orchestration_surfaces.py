"""Phase 9.6 — saved-workflow API, the sub-agent mailbox, template roles."""

from __future__ import annotations

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

import app.db as dbmod
from app.db.sqlite_backend import SQLiteBackend
from app.kernel.toolplane import ExecContext, tool_plane
from app.kernel.types import (
    SubAgentSpec,
    TextBlock,
    ToolUseBlock,
    TurnDone,
    TurnResult,
    Usage,
    WorkflowSpec,
    WorkflowStage,
)
from app.services import sessions as svc
from app.services.orchestration import runner, subagent
from app.services.orchestration.compiler import compile_workflow


@pytest.fixture
def db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    backend = SQLiteBackend(path)
    asyncio.new_event_loop().run_until_complete(backend.initialize())
    monkeypatch.setattr(dbmod, "_db", backend)
    yield backend
    os.remove(path)


_SPEC = {
    "title": "Sweep",
    "worker_model": "fake-model",
    "verify": False,
    "stages": [
        {"id": "s", "kind": "single",
         "agents": [{"role": "w", "prompt": "do it", "tools": []}]},
    ],
}


class _EchoRegistry:
    async def stream(self, messages, model, *, tools=None):
        yield TurnDone(turn=TurnResult(
            blocks=[TextBlock("done")], stop_reason="end",
            usage=Usage(input_tokens=1, output_tokens=1),
            model=model or "m", provider="fake",
        ))


# --- saved workflows API ---


def test_workflows_endpoints_list_and_run(db, auth_client, monkeypatch):
    monkeypatch.setenv("FORGE_SESSIONS", "1")
    assert auth_client.get("/api/workflows").json() == []

    created = auth_client.post("/api/sessions", json={"title": "x"}).json()
    session = svc.get_session(created["id"], created["user_id"])
    saved = runner.save_workflow(session, _SPEC, name="Sweep v1")

    listed = auth_client.get("/api/workflows").json()
    assert [w["name"] for w in listed] == ["Sweep v1"]
    assert listed[0]["workflow_spec"]["title"] == "Sweep"

    with patch("app.providers.registry.create_user_registry",
               AsyncMock(return_value=_EchoRegistry())), \
         patch("app.services.orchestration.subagent.tool_plane.list_tools",
               AsyncMock(return_value=[])):
        r = auth_client.post(f"/api/workflows/{saved['id']}/run", json={})
    assert r.status_code == 200
    assert "workflow_done" in r.text

    # unknown id → 404; a blueprint without a spec → 422
    assert auth_client.post("/api/workflows/nope/run", json={}).status_code == 404


# --- mailbox ---


@pytest.mark.asyncio
async def test_mailbox_tools_exist_only_inside_enabled_runs(db):
    ctx_off = ExecContext(user_id="u1", run_id="run-x")
    names = {s.name for s in await tool_plane.list_tools("u1", ctx_off)}
    assert "mailbox.send" not in names

    subagent.enable_mailbox("run-x", "group-1", ["a", "b"])
    try:
        names = {s.name for s in await tool_plane.list_tools("u1", ctx_off)}
        assert {"mailbox.send", "mailbox.read"} <= names
    finally:
        subagent.disable_mailbox("run-x")
    names = {s.name for s in await tool_plane.list_tools("u1", ctx_off)}
    assert "mailbox.send" not in names


@pytest.mark.asyncio
async def test_mailbox_send_and_read_round_trip(db):
    # anchor row for the FK
    db.table("task_groups").insert(
        {"id": "grp-1", "user_id": "u1", "objective": "t", "status": "running"}
    ).execute()
    subagent.enable_mailbox("run-m", "grp-1", ["scout-1", "scout-2"])
    try:
        ctx_a = ExecContext(user_id="u1", run_id="run-m", agent_label="scout-1")
        ctx_b = ExecContext(user_id="u1", run_id="run-m", agent_label="scout-2")
        sent = await tool_plane.execute(
            ToolUseBlock(id="t1", name="mailbox.send",
                         input={"to": "scout-2", "content": "route /a is yours"}),
            ctx_a,
        )
        assert not sent.is_error
        got = await tool_plane.execute(
            ToolUseBlock(id="t2", name="mailbox.read", input={}), ctx_b
        )
        assert not got.is_error
        assert "route /a is yours" in got.output
        assert "scout-1" in got.output  # sender resolved back to its node id
    finally:
        subagent.disable_mailbox("run-m")


@pytest.mark.asyncio
async def test_workflow_run_gets_a_task_group_mailbox(db):
    s = svc.create_session("u1", model="fake-model")
    with patch("app.providers.registry.create_user_registry",
               AsyncMock(return_value=_EchoRegistry())), \
         patch("app.services.orchestration.subagent.tool_plane.list_tools",
               AsyncMock(return_value=[])):
        events = [e async for e in runner.run_workflow(s, _SPEC)]
    run_id = events[0]["data"]["run_id"]
    groups = db.table("task_groups").select("*").eq("id", run_id).execute().data
    assert len(groups) == 1
    assert groups[0]["status"] == "completed"
    assert run_id not in subagent._MAILBOXES  # cleaned up


# --- template roles ---


def test_role_matching_a_saved_template_inherits_its_prompt(db):
    db.table("agents").insert({
        "id": "tmpl-1", "user_id": "u1", "name": "Researcher",
        "description": "desk research", "system_prompt": "You are a meticulous researcher.",
    }).execute()
    spec = WorkflowSpec(title="T", stages=[
        WorkflowStage(id="a", agents=[
            SubAgentSpec(role="Researcher", prompt="Find recent papers."),
        ]),
    ])
    bp = compile_workflow(spec, user_id="u1")
    prompt = bp["nodes"][0]["config"]["spec"]["prompt"]
    assert prompt.startswith("You are a meticulous researcher.")
    assert "Find recent papers." in prompt

    # ephemeral rows never act as templates
    db.table("agents").insert({
        "id": "eph-1", "user_id": "u1", "name": "Ghost",
        "description": "", "system_prompt": "SHOULD NOT LEAK", "ephemeral": 1,
    }).execute()
    spec2 = WorkflowSpec(title="T2", stages=[
        WorkflowStage(id="a", agents=[SubAgentSpec(role="Ghost", prompt="hi")]),
    ])
    bp2 = compile_workflow(spec2, user_id="u1")
    assert "SHOULD NOT LEAK" not in bp2["nodes"][0]["config"]["spec"]["prompt"]
