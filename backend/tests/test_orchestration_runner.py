"""Phase 9.5 — consented workflow execution, progress events, save-to-library."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

import app.db as dbmod
from app.db.sqlite_backend import SQLiteBackend
from app.kernel.types import TextBlock, TurnDone, TurnResult, Usage
from app.services import sessions as svc
from app.services.orchestration import runner


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
    "title": "Audit routers",
    "rationale": "One scout per router.",
    "worker_model": "fake-model",
    "stages": [
        {"id": "scout", "kind": "fanout", "agents": [
            {"role": "scout", "prompt": "Audit x.py", "tools": [],
             "success_criteria": "cites routes"},
            {"role": "scout", "prompt": "Audit y.py", "tools": [],
             "success_criteria": "cites routes"},
        ]},
    ],
    "verify": False,
}


class _EchoRegistry:
    async def stream(self, messages, model, *, tools=None):
        yield TurnDone(turn=TurnResult(
            blocks=[TextBlock("scout findings")], stop_reason="end",
            usage=Usage(input_tokens=5, output_tokens=7),
            model=model or "m", provider="fake",
        ))


def _patches(registry=None):
    return (
        patch("app.providers.registry.create_user_registry",
              AsyncMock(return_value=registry or _EchoRegistry())),
        patch("app.services.orchestration.subagent.tool_plane.list_tools",
              AsyncMock(return_value=[])),
    )


@pytest.mark.asyncio
async def test_run_workflow_streams_progress_and_persists_outcome(db):
    s = svc.create_session("u1", model="fake-model")
    p1, p2 = _patches()
    with p1, p2:
        events = [e async for e in runner.run_workflow(
            s, _SPEC, goal="audit the routers", plan_seq=3,
        )]

    types = [e["type"] for e in events]
    assert types[0] == "workflow_started"
    assert events[0]["data"]["stages"] == [{"id": "scout", "agents_total": 2}]
    progress = [e for e in events if e["type"] == "workflow_progress"]
    assert progress, "expected live progress events"
    assert progress[-1]["data"]["agents_done"] == 2
    assert progress[-1]["data"]["tokens_spent"] == 24  # 2 × (5+7)
    done = events[-1]
    assert done["type"] == "workflow_done"
    assert done["data"]["status"] == "completed"
    assert done["data"]["agents_run"] == 2
    assert "scout findings" in done["data"]["output"]

    # persisted into the session log: run marker, done marker, and a
    # conversation-visible note the model can use next turn
    kinds = [e["kind"] for e in svc.get_events(s["id"])]
    assert "workflow_run" in kinds and "workflow_done" in kinds
    msgs = svc.build_messages(svc.get_session(s["id"], "u1"))
    assert any("[workflow 'Audit routers' completed]" in b.text
               for m in msgs for b in m.blocks if isinstance(b, TextBlock))

    # ephemeral agent rows were spawned and sub-agent transcripts recorded
    agents = db.table("agents").select("*").eq("user_id", "u1").execute().data
    assert len(agents) == 2 and all(a["ephemeral"] for a in agents)
    runs = db.table("runs").select("*").eq("user_id", "u1").execute().data
    assert len(runs) == 2
    assert all(r["status"] == "completed" for r in runs)
    run_events = db.table("run_events").select("*").execute().data
    assert any(e["event_type"] == "model_call" for e in run_events)
    assert any(e["event_type"] == "run_end" for e in run_events)


@pytest.mark.asyncio
async def test_run_workflow_surfaces_compile_errors(db):
    s = svc.create_session("u1", model="fake-model")
    bad = {**_SPEC, "max_agents_total": 1}
    events = [e async for e in runner.run_workflow(s, bad)]
    assert events == [{"type": "error",
                       "data": events[0]["data"]}]
    assert "ceiling" in events[0]["data"]


def test_save_workflow_persists_blueprint_without_spawning_agents(db):
    s = svc.create_session("u1", model="fake-model")
    saved = runner.save_workflow(s, _SPEC, name="Router audit v1")
    assert saved["name"] == "Router audit v1"
    rows = db.table("blueprints").select("*").eq("user_id", "u1").execute().data
    assert len(rows) == 1
    cc = rows[0]["context_config"]
    if isinstance(cc, str):
        cc = json.loads(cc)
    assert cc["workflow_spec"]["title"] == "Audit routers"
    nodes = rows[0]["nodes"]
    if isinstance(nodes, str):
        nodes = json.loads(nodes)
    assert [n["type"] for n in nodes] == ["subagent_run", "subagent_run"]
    # save spawns nothing
    assert db.table("agents").select("*").eq("user_id", "u1").execute().data in ([], None)
    # and it shows up in the saved-workflows listing
    listed = runner.list_saved_workflows("u1")
    assert len(listed) == 1 and listed[0]["workflow_spec"]["title"] == "Audit routers"


@pytest.mark.asyncio
async def test_saved_workflow_reruns_with_identical_structure(db):
    s = svc.create_session("u1", model="fake-model")
    saved = runner.save_workflow(s, _SPEC)
    rows = db.table("blueprints").select("*").eq("id", saved["id"]).execute().data
    cc = rows[0]["context_config"]
    if isinstance(cc, str):
        cc = json.loads(cc)
    p1, p2 = _patches()
    with p1, p2:
        events = [e async for e in runner.run_workflow(s, cc["workflow_spec"])]
    assert events[-1]["data"]["status"] == "completed"
    assert events[0]["data"]["stages"] == [{"id": "scout", "agents_total": 2}]


def test_get_plan_reads_the_session_log(db):
    s = svc.create_session("u1", model="fake-model")
    seq = svc.append_event(s["id"], "workflow_plan",
                           {"spec": _SPEC, "goal": "g", "status": "proposed"})
    plan = runner.get_plan(s["id"], seq)
    assert plan is not None and plan["spec"]["title"] == "Audit routers"
    assert runner.get_plan(s["id"], seq + 99) is None


def test_run_endpoint_enforces_confirm_threshold(db, auth_client, monkeypatch):
    monkeypatch.setenv("FORGE_SESSIONS", "1")
    monkeypatch.setenv("FORGE_WORKFLOW_CONFIRM_THRESHOLD", "1")
    created = auth_client.post("/api/sessions", json={"title": "x"}).json()

    r = auth_client.post(
        f"/api/sessions/{created['id']}/workflow/run", json={"spec": _SPEC}
    )
    assert r.status_code == 400
    assert "confirm=true" in r.json()["detail"]

    # with confirm, the run is accepted (fake providers; SSE stream completes)
    with patch("app.providers.registry.create_user_registry",
               AsyncMock(return_value=_EchoRegistry())), \
         patch("app.services.orchestration.subagent.tool_plane.list_tools",
               AsyncMock(return_value=[])):
        r = auth_client.post(
            f"/api/sessions/{created['id']}/workflow/run",
            json={"spec": _SPEC, "confirm": True},
        )
    assert r.status_code == 200
    assert "workflow_done" in r.text


def test_save_endpoint_resolves_a_stored_plan(db, auth_client, monkeypatch):
    monkeypatch.setenv("FORGE_SESSIONS", "1")
    created = auth_client.post("/api/sessions", json={"title": "x"}).json()
    # find the session's owner id (the auth_client user) via the API row
    seq = svc.append_event(created["id"], "workflow_plan",
                           {"spec": _SPEC, "goal": "g", "status": "proposed"})
    r = auth_client.post(
        f"/api/sessions/{created['id']}/workflow/save",
        json={"plan_seq": seq, "name": "From plan"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "From plan"
    # a bad seq 404s
    r = auth_client.post(
        f"/api/sessions/{created['id']}/workflow/save", json={"plan_seq": 9999}
    )
    assert r.status_code == 404
