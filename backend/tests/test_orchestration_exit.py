"""Phase 9.7 — dynamic-orchestration exit criteria.

Golden compile snapshot, flat parent context over a 50-item corpus,
cancellation mid-fanout, budget exhaustion halting new agents, and the
ephemeral-agents list filter. (Concurrency cap, verify-retry, and saved-rerun
are covered in the 9.3/9.4/9.5 suites.)
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import app.db as dbmod
from app.db.sqlite_backend import SQLiteBackend
from app.kernel.types import TextBlock, TurnDone, TurnResult, Usage
from app.services import sessions as svc
from app.services.orchestration import runner
from app.services.orchestration.compiler import compile_workflow

from .parity._harness import assert_golden


@pytest.fixture
def db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    backend = SQLiteBackend(path)
    asyncio.new_event_loop().run_until_complete(backend.initialize())
    monkeypatch.setattr(dbmod, "_db", backend)
    yield backend
    os.remove(path)


class _EchoRegistry:
    def __init__(self, text="item processed", delay=0.0):
        self.text = text
        self.delay = delay
        self.started = 0
        self.finished = 0

    async def stream(self, messages, model, *, tools=None):
        self.started += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        self.finished += 1
        yield TurnDone(turn=TurnResult(
            blocks=[TextBlock(self.text)], stop_reason="end",
            usage=Usage(input_tokens=100, output_tokens=200),
            model=model or "m", provider="fake",
        ))


def _patches(registry):
    return (
        patch("app.providers.registry.create_user_registry",
              AsyncMock(return_value=registry)),
        patch("app.services.orchestration.subagent.tool_plane.list_tools",
              AsyncMock(return_value=[])),
    )


def _fanout_spec(n: int, max_concurrent: int = 16) -> dict:
    return {
        "title": f"Corpus sweep ({n})",
        "worker_model": "fake-model",
        "verify": False,
        "max_concurrent": max_concurrent,
        "stages": [{
            "id": "fan", "kind": "fanout",
            "agents": [
                {"role": "worker", "prompt": f"Process item {i}.", "tools": [],
                 "inputs": {"item": i}, "success_criteria": "item processed"}
                for i in range(n)
            ],
        }],
    }


# --- golden: a fixed planner output compiles to a deterministic blueprint ---


def test_fixed_plan_compiles_to_golden_snapshot(db):
    from app.kernel.serialize import workflow_spec_from_dict

    spec = workflow_spec_from_dict({
        "title": "Audit every router",
        "rationale": "One scout per router file, adversarially verified.",
        "worker_model": "fake-model",
        "max_concurrent": 4,
        "stages": [
            {"id": "scout", "kind": "fanout", "agents": [
                {"role": "scout", "prompt": "Audit routers/a.py for missing auth.",
                 "tools": ["workspace.read"], "success_criteria": "cites routes",
                 "inputs": {"file": "routers/a.py"}, "outputs": ["findings"]},
                {"role": "scout", "prompt": "Audit routers/b.py for missing auth.",
                 "tools": ["workspace.read"], "success_criteria": "cites routes",
                 "inputs": {"file": "routers/b.py"}, "outputs": ["findings"]},
            ]},
            {"id": "verify", "kind": "verify", "depends_on": ["scout"], "agents": [
                {"role": "reviewer", "prompt": "Judge each scout.", "tools": []},
            ]},
        ],
    })
    # create_agents=False keeps the snapshot free of per-run uuids.
    bp = compile_workflow(spec, user_id="golden-user", create_agents=False)
    assert_golden("workflow_compile_audit", bp)


# --- flat parent context over a 50-item corpus ---


@pytest.mark.asyncio
async def test_parent_context_stays_flat_over_a_50_item_corpus(db):
    s = svc.create_session("u1", model="fake-model")
    before = svc._estimate_tokens(svc.build_messages(s))

    registry = _EchoRegistry(text="item processed: " + "x" * 400)
    p1, p2 = _patches(registry)
    with p1, p2:
        events = [e async for e in runner.run_workflow(s, _fanout_spec(50))]

    assert events[-1]["data"]["status"] == "completed"
    assert registry.finished == 50  # the corpus was actually processed

    after = svc._estimate_tokens(svc.build_messages(svc.get_session(s["id"], "u1")))
    # Intermediate state lives in DAG edges (and sub-agent runs), not the
    # parent context: 50 agents × ~500 chars each would be ~6k tokens if they
    # leaked in; the parent only gains the final workflow note.
    assert after - before < 1500
    sub_runs = db.table("runs").select("id").eq("user_id", "u1").execute().data
    assert len(sub_runs) == 50  # ...while each sub-agent kept its own transcript


# --- cancellation mid-fanout stops all children ---


@pytest.mark.asyncio
async def test_cancellation_mid_fanout_stops_all_children(db):
    import contextlib

    s = svc.create_session("u1", model="fake-model")
    registry = _EchoRegistry(delay=0.5)
    events: list = []
    p1, p2 = _patches(registry)
    with p1, p2:
        gen = runner.run_workflow(s, _fanout_spec(6, max_concurrent=2))

        async def consume():
            async for e in gen:
                events.append(e)

        task = asyncio.create_task(consume())
        for _ in range(200):  # wait until children are actually in flight
            await asyncio.sleep(0.01)
            if registry.started > 0:
                break
        assert registry.started > 0
        started_at_cancel = registry.started
        task.cancel()  # the client disconnected mid-fanout
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.7)  # give any survivors time to finish (they must not)

    assert registry.started == started_at_cancel  # queued children never started
    assert started_at_cancel < 6
    assert registry.finished == 0  # in-flight children were cancelled, not completed


# --- budget exhaustion halts scheduling of new agents ---


@pytest.mark.asyncio
async def test_budget_exhaustion_halts_new_agents(db):
    s = svc.create_session("u1", model="fake-model")
    registry = _EchoRegistry()
    exhausted = SimpleNamespace(within_budget=False, limit_usd=1.0, spent_usd=1.5)
    p1, p2 = _patches(registry)
    with p1, p2, patch("app.services.budgets.check_user_budget",
                       return_value=exhausted):
        events = [e async for e in runner.run_workflow(s, _fanout_spec(4))]

    assert registry.started == 0  # nothing was scheduled
    assert events[-1]["data"]["status"] == "failed"
    assert any(e["type"] == "workflow_error" and "budget" in e["data"]["error"]
               for e in events)


# --- ephemeral agents are hidden from the default list, visible with a filter ---


def test_ephemeral_agents_hidden_from_default_list(db, auth_client, monkeypatch):
    monkeypatch.setenv("FORGE_SESSIONS", "1")
    session = auth_client.post("/api/sessions", json={"title": "x"}).json()
    user_id = session["user_id"]
    db.table("agents").insert({
        "id": "a-normal", "user_id": user_id, "name": "Normal",
        "description": "", "system_prompt": "p",
    }).execute()
    db.table("agents").insert({
        "id": "a-eph", "user_id": user_id, "name": "Workflow child",
        "description": "", "system_prompt": "p", "ephemeral": 1,
        "spawned_by_session": session["id"],
    }).execute()

    default = auth_client.get("/api/agents").json()
    assert [a["id"] for a in default] == ["a-normal"]

    everything = auth_client.get("/api/agents?include_ephemeral=true").json()
    ids = {a["id"] for a in everything}
    assert {"a-normal", "a-eph"} <= ids
    eph = next(a for a in everything if a["id"] == "a-eph")
    assert eph["ephemeral"] is True
    assert eph["spawned_by_session"] == session["id"]
