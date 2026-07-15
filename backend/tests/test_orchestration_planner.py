"""Phase 9.2 — the workflow planner and its session trigger.

The planner turns a goal + capability inventory into a WorkflowSpec on the
session's model; its template is versioned as planner/v1; sessions gain an
``effort`` column that gates automatic planning; ``orchestrate.plan`` is a safe
builtin tool.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

import app.db as dbmod
from app.db.sqlite_backend import SQLiteBackend
from app.kernel.toolplane import ExecContext, ToolPlane
from app.kernel.types import TextBlock, TurnResult, Usage
from app.services import sessions as svc
from app.services.orchestration import planner


@pytest.fixture
def db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    backend = SQLiteBackend(path)
    asyncio.new_event_loop().run_until_complete(backend.initialize())
    monkeypatch.setattr(dbmod, "_db", backend)
    yield backend
    os.remove(path)


_SPEC_JSON = json.dumps({
    "title": "Audit routers",
    "rationale": "One scout per router.",
    "stages": [
        {"id": "scout", "kind": "fanout", "agents": [
            {"role": "scout", "prompt": "Audit x.py", "tools": ["workspace.read"],
             "success_criteria": "cites routes", "outputs": ["findings"]},
        ]},
        {"id": "check", "kind": "verify", "depends_on": ["scout"],
         "agents": [{"role": "reviewer", "prompt": "Judge the findings."}]},
    ],
})


class _ScriptedRegistry:
    """Returns scripted turn() replies in order (classify, then plan, ...)."""

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[str | None] = []

    async def turn(self, messages, model=None, **kw):
        self.calls.append(model)
        text = self.replies.pop(0) if self.replies else "no"
        return TurnResult(
            blocks=[TextBlock(text)], stop_reason="end",
            usage=Usage(input_tokens=3, output_tokens=4),
            model=model or "m", provider="fake",
        )

    async def stream(self, messages, model, *, tools=None):
        from app.kernel.types import TurnDone

        yield TurnDone(turn=TurnResult(
            blocks=[TextBlock("normal reply")], stop_reason="end",
            usage=Usage(input_tokens=1, output_tokens=1),
            model=model or "m", provider="fake",
        ))


def _ctx(session_id=""):
    return ExecContext(user_id="u1", session_id=session_id)


@pytest.mark.asyncio
async def test_plan_workflow_parses_spec_and_defaults_worker_model(db):
    registry = _ScriptedRegistry([f"```json\n{_SPEC_JSON}\n```"])
    spec = await planner.plan_workflow(
        "audit every router", user_id="u1", model="gpt-4o",
        registry=registry, ctx=_ctx(),
    )
    assert spec.title == "Audit routers"
    assert spec.stages[0].kind == "fanout"
    # planner ran on the session's model
    assert registry.calls == ["gpt-4o"]
    # worker_model defaulted to the cheapest tools-capable card
    assert spec.worker_model == planner.cheapest_worker_model()
    assert spec.worker_model is not None


@pytest.mark.asyncio
async def test_planner_template_is_versioned_and_reused(db):
    registry = _ScriptedRegistry([_SPEC_JSON, _SPEC_JSON])
    await planner.plan_workflow("goal one", user_id="u1", model=None,
                                registry=registry, ctx=_ctx())
    versions = (
        db.table("prompt_versions").select("*")
        .eq("agent_id", f"{planner.PLANNER_AGENT_PREFIX}u1").execute().data
    )
    assert len(versions) == 1
    assert versions[0]["change_summary"] == "planner/v1 (seeded)"
    # Second plan reuses the active version — no new row.
    await planner.plan_workflow("goal two", user_id="u1", model=None,
                                registry=registry, ctx=_ctx())
    versions = (
        db.table("prompt_versions").select("*")
        .eq("agent_id", f"{planner.PLANNER_AGENT_PREFIX}u1").execute().data
    )
    assert len(versions) == 1


@pytest.mark.asyncio
async def test_orchestrate_plan_is_a_safe_builtin_tool(db):
    plane = ToolPlane()
    specs = {s.name: s for s in await plane.list_tools("u1", _ctx())}
    assert "orchestrate.plan" in specs
    assert specs["orchestrate.plan"].danger_level == "safe"
    assert specs["orchestrate.plan"].input_schema["required"] == ["goal"]


@pytest.mark.asyncio
async def test_ultra_session_proposes_a_plan_instead_of_a_normal_turn(db):
    s = svc.create_session("u1", model="gpt-4o", effort="ultra")
    assert s["effort"] == "ultra"
    # classify → yes, then the plan
    registry = _ScriptedRegistry(["yes", _SPEC_JSON])
    with patch("app.providers.registry.create_user_registry",
               AsyncMock(return_value=registry)):
        events = [e async for e in svc.run_turn(
            s["id"], "u1", "Please audit every router file for missing auth checks."
        )]

    plans = [e for e in events if e["type"] == "workflow_plan"]
    assert len(plans) == 1
    assert plans[0]["data"]["spec"]["title"] == "Audit routers"
    assert plans[0]["data"]["status"] == "proposed"
    assert plans[0]["data"]["estimated_tokens"] > 0
    # the plan is proposed, not executed — no normal assistant tokens
    assert not [e for e in events if e["type"] == "token"]
    # and it is persisted as a session event
    kinds = [e["kind"] for e in svc.get_events(s["id"])]
    assert "workflow_plan" in kinds


@pytest.mark.asyncio
async def test_standard_session_needs_the_keyword(db):
    s = svc.create_session("u1", model="gpt-4o")  # default effort=standard
    registry = _ScriptedRegistry([_SPEC_JSON])
    with patch("app.providers.registry.create_user_registry",
               AsyncMock(return_value=registry)):
        events = [e async for e in svc.run_turn(
            s["id"], "u1", "Please audit every router file for missing auth checks."
        )]
    assert not [e for e in events if e["type"] == "workflow_plan"]

    registry2 = _ScriptedRegistry([_SPEC_JSON])
    with patch("app.providers.registry.create_user_registry",
               AsyncMock(return_value=registry2)):
        events = [e async for e in svc.run_turn(
            s["id"], "u1", "Use a workflow to audit every router for auth checks."
        )]
    assert [e for e in events if e["type"] == "workflow_plan"]


@pytest.mark.asyncio
async def test_ultra_short_or_chatty_messages_run_normally(db):
    s = svc.create_session("u1", model="gpt-4o", effort="ultra")
    registry = _ScriptedRegistry([])  # classification never called for "thanks!"
    with patch("app.providers.registry.create_user_registry",
               AsyncMock(return_value=registry)):
        events = [e async for e in svc.run_turn(s["id"], "u1", "thanks!")]
    assert not [e for e in events if e["type"] == "workflow_plan"]
    assert [e for e in events if e["type"] == "turn_done"]

    # long but conversational → classifier says no → normal turn
    registry2 = _ScriptedRegistry(["no"])
    with patch("app.providers.registry.create_user_registry",
               AsyncMock(return_value=registry2)):
        events = [e async for e in svc.run_turn(
            s["id"], "u1",
            "I was wondering how you have been doing today, any thoughts on things?",
        )]
    assert not [e for e in events if e["type"] == "workflow_plan"]


@pytest.mark.asyncio
async def test_planner_failure_falls_back_to_a_normal_turn(db):
    s = svc.create_session("u1", model="gpt-4o", effort="ultra")
    registry = _ScriptedRegistry(["yes", "I cannot produce a plan, sorry."])
    with patch("app.providers.registry.create_user_registry",
               AsyncMock(return_value=registry)):
        events = [e async for e in svc.run_turn(
            s["id"], "u1", "Please audit every router file for missing auth checks."
        )]
    assert not [e for e in events if e["type"] == "workflow_plan"]
    assert [e for e in events if e["type"] == "turn_done"]


def test_effort_round_trips_via_router(db, auth_client, monkeypatch):
    monkeypatch.setenv("FORGE_SESSIONS", "1")
    created = auth_client.post(
        "/api/sessions", json={"title": "Chat", "effort": "ultra"}
    ).json()
    assert created["effort"] == "ultra"
    patched = auth_client.patch(
        f"/api/sessions/{created['id']}", json={"effort": "standard"}
    ).json()
    assert patched["effort"] == "standard"
    # invalid effort is rejected by validation
    bad = auth_client.post("/api/sessions", json={"effort": "warp"})
    assert bad.status_code == 422
