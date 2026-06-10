"""Tests for the time-travel run debugger (record / replay / edit-and-fork).

These run against a real in-memory SQLite backend so the append-only event log is
verified end to end. The model is mocked at one seam: ``provider_registry.complete``
is replaced with an AsyncMock whose output depends on the system prompt, so we can
assert exactly when (and whether) the model is invoked.

Key invariants under test:

* recording produces a faithful, ordered, append-only event log;
* replay reconstructs identical step state/output from the log with ZERO model
  calls (the provider is asserted never-called during replay);
* fork copies the unchanged prefix and serves it from cache — the model is only
  called for the edited step and the steps after it — and produces a new run id;
* an edit at step N changes downstream output but not the cached prefix.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent_executor import AgentRunner
from app.services.timetravel import (
    ResponseCache,
    RunRecorder,
    build_timeline,
    fork_service,
    load_events,
    replay_with_executor,
)
from app.services.timetravel.cache import CacheMiss


def _run(coro):
    """Run a coroutine on a fresh event loop set as current.

    A fresh loop per call avoids 'no current event loop' / reused-loop issues
    when a test drives several async operations against the SQLite backend.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        asyncio.set_event_loop(asyncio.new_event_loop())


@dataclass
class _FakeLLMResponse:
    content: str
    model: str = "fake-model"
    input_tokens: int = 3
    output_tokens: int = 5
    finish_reason: str = "stop"
    latency_ms: float = 1.0
    provider: str = "fake"
    raw_response: object = None


@pytest.fixture
def sqlite_backend(tmp_path):
    """Real, fully-initialized SQLite backend wired in as the global db."""
    import app.db as db_mod
    from app.db import init_db
    from app.db.sqlite_backend import SQLiteBackend

    previous = db_mod._db
    db = SQLiteBackend(db_path=str(tmp_path / "timetravel.db"))
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(db.initialize())
    finally:
        loop.close()
    asyncio.set_event_loop(asyncio.new_event_loop())
    init_db(db)
    try:
        yield db
    finally:
        db_mod._db = previous


def _seed_run(db, *, user_id: str, agent_id: str | None = None) -> str:
    """Insert a run row and return its id."""
    run_id = str(uuid.uuid4())
    db.table("runs").insert({
        "id": run_id,
        "agent_id": agent_id,
        "user_id": user_id,
        "input_text": "hello",
        "status": "running",
    }).execute()
    return run_id


def _agent_config(prompt: str = "You are helpful", steps: int = 3) -> dict:
    return {
        "id": None,
        "name": "tt-agent",
        "system_prompt": prompt,
        "tools": [],
        "workflow_steps": [f"do step {i}" for i in range(1, steps + 1)],
        "model": "fake-model",
    }


def _make_complete_mock(prompt_marker: str = "PROMPT"):
    """An AsyncMock for provider_registry.complete.

    The response content encodes the system prompt and a per-call counter so
    different prompts and different call orders are distinguishable.
    """
    counter = {"n": 0}

    async def _complete(*, messages, model, temperature):  # noqa: ARG001
        counter["n"] += 1
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        # Tag the output with the prompt so an edited prompt yields different text.
        marker = prompt_marker if prompt_marker in system else "BASE"
        return _FakeLLMResponse(content=f"[{marker}] step-output #{counter['n']}")

    mock = AsyncMock(side_effect=_complete)
    return mock, counter


async def _record_run(db, *, user_id: str, prompt: str = "You are helpful", steps: int = 3):
    """Execute a run with a recorder and return (run_id, complete_mock)."""
    run_id = _seed_run(db, user_id=user_id)
    mock, _counter = _make_complete_mock()
    runner = AgentRunner(recorder=RunRecorder(run_id))
    with patch("app.providers.registry.provider_registry.complete", mock):
        async for _ in runner.execute(_agent_config(prompt, steps), "hello", run_id=run_id):
            pass
    return run_id, mock


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------


def test_recording_produces_append_only_log(sqlite_backend):
    db = sqlite_backend
    run_id, mock = _run(
        _record_run(db, user_id="u1", steps=3)
    )

    events = load_events(run_id)
    types = [e["event_type"] for e in events]

    # Append-only: seq is strictly increasing from 0.
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs)
    assert seqs == list(range(len(events)))

    # Faithful: a run_start, one boundary + one model_call + one state per step,
    # then a run_end.
    assert types[0] == "run_start"
    assert types[-1] == "run_end"
    assert types.count("step_boundary") == 3
    assert types.count("model_call") == 3
    assert types.count("state") == 3

    # The model was actually called once per step during the original run.
    assert mock.await_count == 3


def test_timeline_reconstructs_steps(sqlite_backend):
    db = sqlite_backend
    run_id, _ = _run(_record_run(db, user_id="u1", steps=2))
    timeline = build_timeline(load_events(run_id))
    assert [s["step"] for s in timeline["steps"]] == [1, 2]
    assert all(s["model_responses"] for s in timeline["steps"])
    assert timeline["output"]


# --------------------------------------------------------------------------
# Replay
# --------------------------------------------------------------------------


def test_replay_is_deterministic_and_calls_no_model(sqlite_backend):
    db = sqlite_backend
    run_id, _ = _run(_record_run(db, user_id="u1", steps=3))
    original = build_timeline(load_events(run_id))

    replay_mock = AsyncMock()
    with patch("app.providers.registry.provider_registry.complete", replay_mock):
        result = _run(replay_with_executor(run_id))

    # The model is NEVER invoked during replay.
    assert replay_mock.await_count == 0

    # Replay reconstructs identical per-step model output.
    orig_outputs = [s["model_responses"][0]["content"] for s in original["steps"]]
    replay_outputs = [s["model_responses"][0]["content"] for s in result["steps"]]
    assert replay_outputs == orig_outputs
    # The executor, re-driven from the strict cache, reproduces each step output.
    for content in orig_outputs:
        assert content in result["replayed_output"]


def test_strict_cache_miss_raises(sqlite_backend):
    db = sqlite_backend
    run_id, _ = _run(_record_run(db, user_id="u1", steps=2))
    events = load_events(run_id)
    # Drop the model_call for step 2 so replay must "pay" for it → CacheMiss.
    events = [e for e in events if not (e["event_type"] == "model_call" and e["step"] == 2)]
    cache = ResponseCache.from_events(events, strict=True)
    cache.reset_cursors()
    assert cache.get_model(1)[0] is True
    with pytest.raises(CacheMiss):
        cache.get_model(2)


# --------------------------------------------------------------------------
# Edit-and-fork
# --------------------------------------------------------------------------


def test_fork_serves_prefix_from_cache_and_only_pays_from_edit(sqlite_backend):
    """Fork at step 2: step 1 is served from cache; steps 2,3 recompute."""
    db = sqlite_backend
    user_id = "u1"
    # Seed a real agent so the fork can read its system prompt.
    agent = db.table("agents").insert({
        "user_id": user_id, "name": "a", "system_prompt": "You are helpful",
        "workflow_steps": ["do step 1", "do step 2", "do step 3"], "model": "fake-model",
    }).execute().data[0]
    agent_id = agent["id"]

    # Record a parent run against that agent.
    run_id = _seed_run(db, user_id=user_id, agent_id=agent_id)
    parent_mock, _ = _make_complete_mock()
    runner = AgentRunner(recorder=RunRecorder(run_id))
    with patch("app.providers.registry.provider_registry.complete", parent_mock):
        _run(
            _drain(runner.execute(_agent_config("You are helpful", 3), "hello", run_id=run_id))
        )
    assert parent_mock.await_count == 3

    parent_events = load_events(run_id)
    parent_step1_output = build_timeline(parent_events)["steps"][0]["model_responses"][0]["content"]

    # Fork from step 2 with no edits — step 1 must be served from cache.
    fork_mock, _ = _make_complete_mock()
    with patch("app.providers.registry.provider_registry.complete", fork_mock):
        result = _run(
            fork_service.fork(parent_run_id=run_id, user_id=user_id, from_step=2, edits={})
        )

    # New run id.
    child_id = result["child_run_id"]
    assert child_id != run_id

    # Only steps 2 and 3 hit the model; step 1 was served from cache (not re-billed).
    assert fork_mock.await_count == 2
    assert result["served_from_cache_steps"] == [1]
    assert result["recomputed_steps"] == [2, 3]

    # The child's copied prefix preserves step 1's recorded output verbatim.
    child_events = load_events(child_id)
    child_step1 = build_timeline(child_events)["steps"][0]
    assert child_step1["model_responses"][0]["content"] == parent_step1_output


def test_fork_with_prompt_edit_changes_downstream_and_recomputes_all(sqlite_backend):
    """A prompt edit invalidates the whole run; downstream output changes."""
    db = sqlite_backend
    user_id = "u1"
    agent = db.table("agents").insert({
        "user_id": user_id, "name": "a", "system_prompt": "You are helpful",
        "workflow_steps": ["do step 1", "do step 2"], "model": "fake-model",
    }).execute().data[0]
    agent_id = agent["id"]

    run_id = _seed_run(db, user_id=user_id, agent_id=agent_id)
    parent_mock, _ = _make_complete_mock()
    runner = AgentRunner(recorder=RunRecorder(run_id))
    with patch("app.providers.registry.provider_registry.complete", parent_mock):
        _run(
            _drain(runner.execute(_agent_config("You are helpful", 2), "hello", run_id=run_id))
        )

    # Fork with a prompt edit containing the marker → output flips to [PROMPT].
    fork_mock, _ = _make_complete_mock()
    with patch("app.providers.registry.provider_registry.complete", fork_mock):
        result = _run(
            fork_service.fork(
                parent_run_id=run_id, user_id=user_id, from_step=2,
                edits={"prompt": "PROMPT: be terse"},
            )
        )

    # Prompt edit forces recompute from step 1 — all steps re-billed.
    assert fork_mock.await_count == 2
    assert result["from_step"] == 1
    assert result["served_from_cache_steps"] == []

    # Downstream output reflects the new prompt.
    child_timeline = build_timeline(load_events(result["child_run_id"]))
    contents = [s["model_responses"][0]["content"] for s in child_timeline["steps"]]
    assert all("[PROMPT]" in c for c in contents)


def test_fork_records_lineage(sqlite_backend):
    db = sqlite_backend
    user_id = "u1"
    agent = db.table("agents").insert({
        "user_id": user_id, "name": "a", "system_prompt": "You are helpful",
        "workflow_steps": ["do step 1", "do step 2"], "model": "fake-model",
    }).execute().data[0]
    run_id = _seed_run(db, user_id=user_id, agent_id=agent["id"])
    parent_mock, _ = _make_complete_mock()
    runner = AgentRunner(recorder=RunRecorder(run_id))
    with patch("app.providers.registry.provider_registry.complete", parent_mock):
        _run(
            _drain(runner.execute(_agent_config("You are helpful", 2), "hello", run_id=run_id))
        )

    fork_mock, _ = _make_complete_mock()
    with patch("app.providers.registry.provider_registry.complete", fork_mock):
        result = _run(
            fork_service.fork(parent_run_id=run_id, user_id=user_id, from_step=2, edits={})
        )

    forks = db.table("run_forks").select("*").eq("child_run_id", result["child_run_id"]).execute().data
    assert len(forks) == 1
    assert forks[0]["parent_run_id"] == run_id
    assert forks[0]["from_step"] == 2


async def _drain(agen):
    async for _ in agen:
        pass


# --------------------------------------------------------------------------
# API routes
# --------------------------------------------------------------------------


def test_events_route_returns_timeline(sqlite_backend, auth_client, mock_user):
    db = sqlite_backend
    run_id, _ = _run(_record_run(db, user_id=mock_user.id, steps=2))
    resp = auth_client.get(f"/api/runs/{run_id}/events")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run_id
    assert len(body["timeline"]["steps"]) == 2


def test_events_route_404_for_other_users_run(sqlite_backend, auth_client, mock_user):
    db = sqlite_backend
    other_run, _ = _run(_record_run(db, user_id="someone-else", steps=1))
    resp = auth_client.get(f"/api/runs/{other_run}/events")
    assert resp.status_code == 404


def test_replay_route_no_model_calls(sqlite_backend, auth_client, mock_user):
    db = sqlite_backend
    run_id, _ = _run(_record_run(db, user_id=mock_user.id, steps=2))
    replay_mock = AsyncMock()
    with patch("app.providers.registry.provider_registry.complete", replay_mock):
        resp = auth_client.post(f"/api/runs/{run_id}/replay")
    assert resp.status_code == 200
    assert replay_mock.await_count == 0
    assert len(resp.json()["steps"]) == 2
