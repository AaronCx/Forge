"""Phase 9.4 — the verification stage.

A reviewer sub-agent judges each producer's output against its
success_criteria; failures route back through one bounded retry of the
producing agent with the findings attached, and the retried output is
re-judged. The planner appends a default verify stage unless verify=false.
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
from app.kernel.types import (
    SubAgentSpec,
    TextBlock,
    TurnDone,
    TurnResult,
    Usage,
    WorkflowSpec,
    WorkflowStage,
)
from app.services.orchestration.planner import ensure_verify_stage
from app.services.orchestration.subagent import execute_subagent_run


@pytest.fixture
def db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    backend = SQLiteBackend(path)
    asyncio.new_event_loop().run_until_complete(backend.initialize())
    monkeypatch.setattr(dbmod, "_db", backend)
    yield backend
    os.remove(path)


# --- planner appends the verify stage ---


def _spec(verify=True, stages=None):
    return WorkflowSpec(
        title="T",
        verify=verify,
        stages=stages or [
            WorkflowStage(id="a", kind="fanout",
                          agents=[SubAgentSpec(role="w", prompt="p")]),
            WorkflowStage(id="b", kind="single", depends_on=["a"],
                          agents=[SubAgentSpec(role="w2", prompt="p2")]),
        ],
    )


def test_verify_stage_is_appended_on_terminal_stages():
    spec = ensure_verify_stage(_spec(), goal="the goal")
    assert spec.stages[-1].kind == "verify"
    assert spec.stages[-1].depends_on == ["b"]  # only the terminal stage
    reviewer = spec.stages[-1].agents[0]
    assert reviewer.role == "reviewer"
    assert "the goal" in reviewer.prompt
    assert reviewer.tools == []  # the judge needs no tools by default


def test_verify_stage_not_appended_when_opted_out_or_present():
    assert ensure_verify_stage(_spec(verify=False)) == _spec(verify=False)
    already = _spec(stages=[
        WorkflowStage(id="a", agents=[SubAgentSpec(role="w", prompt="p")]),
        WorkflowStage(id="v", kind="verify", depends_on=["a"],
                      agents=[SubAgentSpec(role="r", prompt="judge")]),
    ])
    assert ensure_verify_stage(already) == already


# --- the verify executor ---


class _ScriptedStreamRegistry:
    """stream() yields one scripted text turn per call, in order."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts: list[str] = []

    async def stream(self, messages, model, *, tools=None):
        # record the full conversation of each call for assertions
        self.prompts.append("\n\n".join(
            b.text for m in messages for b in m.blocks if isinstance(b, TextBlock)
        ))
        text = self.replies.pop(0) if self.replies else "{}"
        yield TurnDone(turn=TurnResult(
            blocks=[TextBlock(text)], stop_reason="end",
            usage=Usage(input_tokens=5, output_tokens=5),
            model=model or "m", provider="fake",
        ))


def _verify_config():
    return {
        "spec": {"role": "reviewer", "prompt": "judge strictly", "tools": []},
        "stage_kind": "verify",
        "worker_model": "fake-model",
        "max_concurrent": 4,
        "workflow_title": "audit the routers",
        "agent_id": "agent-v",
    }


def _producer_inputs():
    return {
        "_user_id": "u1", "_run_id": "r-verify", "_node_id": "verify",
        "text": "combined upstream",
        "result_scout-1": {
            "node_id": "scout-1", "role": "scout",
            "success_criteria": "cites every route",
            "text": "WRONG: no routes cited",
            "spec": {"role": "scout", "prompt": "audit routes", "tools": []},
            "user_prompt": "Audit file X.",
        },
        "result_scout-2": {
            "node_id": "scout-2", "role": "scout",
            "success_criteria": "cites every route",
            "text": "GOOD: routes /a and /b cited",
            "spec": {"role": "scout", "prompt": "audit routes", "tools": []},
            "user_prompt": "Audit file Y.",
        },
    }


@pytest.mark.asyncio
async def test_seeded_wrong_answer_is_caught_and_corrected_on_retry(db):
    registry = _ScriptedStreamRegistry([
        # 1) first review: scout-1 fails, scout-2 passes
        json.dumps({"items": [
            {"node_id": "scout-1", "verdict": "fail", "findings": "no routes cited"},
            {"node_id": "scout-2", "verdict": "pass", "findings": ""},
        ]}),
        # 2) the retried producer's corrected output
        "CORRECTED: routes /x and /y cited",
        # 3) re-judge of the retried item
        json.dumps({"items": [
            {"node_id": "scout-1", "verdict": "pass", "findings": ""},
        ]}),
    ])
    with (
        patch("app.providers.registry.create_user_registry",
              AsyncMock(return_value=registry)),
        patch("app.services.orchestration.subagent.tool_plane.list_tools",
              AsyncMock(return_value=[])),
    ):
        out = await execute_subagent_run(_verify_config(), _producer_inputs())

    assert out["verdicts"] == {"scout-1": "pass", "scout-2": "pass"}
    items = {i["node_id"]: i for i in out["items"]}
    assert items["scout-1"]["retried"] is True
    assert items["scout-1"]["text"] == "CORRECTED: routes /x and /y cited"
    assert items["scout-2"]["retried"] is False
    # the retry prompt carried the findings and the original task context
    retry_prompt = registry.prompts[1]
    assert "no routes cited" in retry_prompt      # findings attached
    assert "Audit file X." in retry_prompt        # original inputs re-seeded
    # tokens from reviewer + retry + re-judge are all accounted
    assert out["input_tokens"] == 15 and out["output_tokens"] == 15
    assert "1 pass" not in out["text"].splitlines()[0]  # summary reads 2 pass
    assert out["text"].startswith("Verification: 2 pass, 0 fail")


@pytest.mark.asyncio
async def test_retry_is_bounded_to_one_attempt(db):
    registry = _ScriptedStreamRegistry([
        json.dumps({"items": [
            {"node_id": "scout-1", "verdict": "fail", "findings": "wrong"},
            {"node_id": "scout-2", "verdict": "pass", "findings": ""},
        ]}),
        "still wrong",
        json.dumps({"items": [
            {"node_id": "scout-1", "verdict": "fail", "findings": "still wrong"},
        ]}),
    ])
    with (
        patch("app.providers.registry.create_user_registry",
              AsyncMock(return_value=registry)),
        patch("app.services.orchestration.subagent.tool_plane.list_tools",
              AsyncMock(return_value=[])),
    ):
        out = await execute_subagent_run(_verify_config(), _producer_inputs())

    # exactly 3 model calls: review, one retry, one re-judge — never a 2nd retry
    assert registry.prompts and len(registry.prompts) == 3
    assert out["verdicts"]["scout-1"] == "fail"
    items = {i["node_id"]: i for i in out["items"]}
    assert items["scout-1"]["retried"] is True


@pytest.mark.asyncio
async def test_unparseable_review_yields_unknown_and_no_retry(db):
    registry = _ScriptedStreamRegistry(["I think they are all fine, great work!"])
    with (
        patch("app.providers.registry.create_user_registry",
              AsyncMock(return_value=registry)),
        patch("app.services.orchestration.subagent.tool_plane.list_tools",
              AsyncMock(return_value=[])),
    ):
        out = await execute_subagent_run(_verify_config(), _producer_inputs())
    assert set(out["verdicts"].values()) == {"unknown"}
    assert len(registry.prompts) == 1  # no retries on unknown


@pytest.mark.asyncio
async def test_verify_without_structured_producers_runs_as_plain_agent(db):
    registry = _ScriptedStreamRegistry(["plain answer"])
    with (
        patch("app.providers.registry.create_user_registry",
              AsyncMock(return_value=registry)),
        patch("app.services.orchestration.subagent.tool_plane.list_tools",
              AsyncMock(return_value=[])),
    ):
        out = await execute_subagent_run(
            _verify_config(),
            {"_user_id": "u1", "_run_id": "r", "_node_id": "v", "text": "ctx"},
        )
    assert out["text"] == "plain answer"
    assert "verdicts" not in out
