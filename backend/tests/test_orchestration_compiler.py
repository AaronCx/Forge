"""Phase 9.3 — the WorkflowSpec→blueprint compiler and the subagent_run node."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

import app.db as dbmod
from app.db.sqlite_backend import SQLiteBackend
from app.kernel.types import (
    BudgetSpec,
    SubAgentSpec,
    TextBlock,
    TurnDone,
    TurnResult,
    Usage,
    WorkflowSpec,
    WorkflowStage,
)
from app.services.orchestration.compiler import WorkflowCompileError, compile_workflow


@pytest.fixture
def db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    backend = SQLiteBackend(path)
    asyncio.new_event_loop().run_until_complete(backend.initialize())
    monkeypatch.setattr(dbmod, "_db", backend)
    yield backend
    os.remove(path)


def _agent(role="scout", **kw):
    return SubAgentSpec(role=role, prompt=f"do {role} work", **kw)


def _spec(**kw):
    defaults = dict(
        title="Audit",
        stages=[
            WorkflowStage(id="scout", kind="fanout",
                          agents=[_agent(), _agent(role="scout2")]),
            WorkflowStage(id="check", kind="verify", depends_on=["scout"],
                          agents=[_agent(role="reviewer")]),
        ],
        worker_model="fake-model",
    )
    defaults.update(kw)
    return WorkflowSpec(**defaults)


def test_compile_produces_layered_dag(db):
    bp = compile_workflow(_spec(), user_id="u1", session_id="s1")
    assert bp["name"] == "Audit"
    nodes = {n["id"]: n for n in bp["nodes"]}
    # fanout → N parallel nodes in one topological layer (same empty deps)
    assert nodes["scout-1"]["dependencies"] == []
    assert nodes["scout-2"]["dependencies"] == []
    # the verify stage depends on every fanout node
    assert sorted(nodes["check"]["dependencies"]) == ["scout-1", "scout-2"]
    assert all(n["type"] == "subagent_run" for n in bp["nodes"])
    # the compiled blueprint is engine-compatible (topology sorts into 2 layers)
    from app.services.blueprint_engine import _topological_sort

    layers = _topological_sort(bp["nodes"])
    assert [sorted(bp["nodes"][i]["id"] for i in layer) for layer in layers] == [
        ["scout-1", "scout-2"], ["check"],
    ]


def test_compile_creates_ephemeral_agent_rows(db):
    bp = compile_workflow(_spec(), user_id="u1", session_id="sess-9")
    rows = db.table("agents").select("*").eq("user_id", "u1").execute().data
    assert len(rows) == 3
    assert all(r["ephemeral"] for r in rows)
    assert all(r["spawned_by_session"] == "sess-9" for r in rows)
    spec_json = json.loads(rows[0]["spec_json"])
    assert spec_json["prompt"].startswith("do ")
    # node configs reference the audit rows
    agent_ids = {r["id"] for r in rows}
    assert {n["config"]["agent_id"] for n in bp["nodes"]} == agent_ids


def test_agent_ceiling_aborts_compilation_not_execution(db):
    spec = _spec(
        stages=[WorkflowStage(id="fan", kind="fanout",
                              agents=[_agent(role=f"a{i}") for i in range(5)])],
        max_agents_total=3,
    )
    with pytest.raises(WorkflowCompileError, match="ceiling"):
        compile_workflow(spec, user_id="u1")
    # nothing was spawned
    assert db.table("agents").select("*").eq("user_id", "u1").execute().data in ([], None)


def test_bad_dags_are_rejected(db):
    with pytest.raises(WorkflowCompileError, match="unknown stage"):
        compile_workflow(_spec(stages=[
            WorkflowStage(id="a", agents=[_agent()], depends_on=["ghost"]),
        ]), user_id="u1")
    with pytest.raises(WorkflowCompileError, match="duplicate"):
        compile_workflow(_spec(stages=[
            WorkflowStage(id="a", agents=[_agent()]),
            WorkflowStage(id="a", agents=[_agent()]),
        ]), user_id="u1")
    with pytest.raises(WorkflowCompileError, match="no agents"):
        compile_workflow(_spec(stages=[WorkflowStage(id="a")]), user_id="u1")
    with pytest.raises(WorkflowCompileError, match="no stages"):
        compile_workflow(_spec(stages=[]), user_id="u1")


def test_policy_and_concurrency_are_carried_into_node_configs(db):
    spec = _spec(max_concurrent=4, stages=[
        WorkflowStage(id="fan", kind="fanout", concurrency=2,
                      agents=[_agent(), _agent(role="b")]),
    ])
    bp = compile_workflow(
        spec, user_id="u1", session_id="s1",
        policy={"cu.drive_run": "deny", "approve_scope": "call"},
        workspace_root="/tmp/ws",
    )
    cfg = bp["nodes"][0]["config"]
    assert cfg["max_concurrent"] == 2  # stage concurrency wins when tighter
    assert cfg["policy"] == {"cu.drive_run": "deny", "approve_scope": "call"}
    assert cfg["workspace_root"] == "/tmp/ws"
    assert cfg["worker_model"] == "fake-model"


class _CountingRegistry:
    """Tracks concurrent stream() calls to prove the fan-out semaphore."""

    def __init__(self):
        self.active = 0
        self.max_active = 0

    async def stream(self, messages, model, *, tools=None):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.02)
        self.active -= 1
        yield TurnDone(turn=TurnResult(
            blocks=[TextBlock("done")], stop_reason="end",
            usage=Usage(input_tokens=2, output_tokens=3),
            model=model or "fake-model", provider="fake",
        ))


@pytest.mark.asyncio
async def test_fanout_semaphore_honors_max_concurrent(db):
    from app.services.blueprint_engine import blueprint_engine
    from app.services.orchestration import subagent

    spec = _spec(
        stages=[WorkflowStage(
            id="fan", kind="fanout",
            agents=[_agent(role=f"a{i}", tools=[]) for i in range(6)],
        )],
        max_concurrent=2,
    )
    bp = compile_workflow(spec, user_id="u1", session_id="s1")
    bp["id"] = "bp-test"
    registry = _CountingRegistry()

    with (
        patch("app.providers.registry.create_user_registry",
              AsyncMock(return_value=registry)),
        patch("app.services.orchestration.subagent.tool_plane.list_tools",
              AsyncMock(return_value=[])),
    ):
        events = [e async for e in blueprint_engine.execute(
            blueprint=bp, input_payload={"text": "go"}, user_id="u1", run_id="run-sem",
        )]
    subagent.release_run("run-sem")

    assert registry.max_active <= 2, f"{registry.max_active} sub-agents ran at once"
    done = [e for e in events if e["type"] == "node_done"]
    assert len(done) == 6
    assert events[-1]["type"] == "result"


@pytest.mark.asyncio
async def test_subagent_gets_scoped_tools_and_never_recursion(db):
    """The allowlist is resolved through the plane; orchestrate.plan and
    node.subagent_run are stripped even under tools='inherit'."""
    from app.services.orchestration.subagent import execute_subagent_run

    captured: dict = {}

    class _SpyRegistry:
        async def stream(self, messages, model, *, tools=None):
            captured["tools"] = tools
            captured["model"] = model
            captured["system"] = messages[0].blocks[0].text
            yield TurnDone(turn=TurnResult(
                blocks=[TextBlock("ok")], stop_reason="end",
                usage=Usage(input_tokens=1, output_tokens=1),
                model=model or "m", provider="fake",
            ))

    with patch("app.providers.registry.create_user_registry",
               AsyncMock(return_value=_SpyRegistry())):
        out = await execute_subagent_run(
            {"spec": {"role": "scout", "prompt": "look", "tools": "inherit",
                      "success_criteria": "finds it"},
             "worker_model": "fake-model", "max_concurrent": 2,
             "workflow_title": "T"},
            {"text": "ctx", "_user_id": "u1", "_run_id": "r1", "_node_id": "n1"},
        )

    names = {t.name for t in (captured["tools"] or [])}
    assert names, "inherit should hand the sub-agent the plane's tools"
    assert "orchestrate.plan" not in names
    assert "node.subagent_run" not in names
    assert captured["model"] == "fake-model"
    assert "finds it" in captured["system"]
    assert out["text"] == "ok"
    assert out["result_n1"]["success_criteria"] == "finds it"
