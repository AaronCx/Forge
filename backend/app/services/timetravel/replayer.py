"""Deterministic replay of a recorded run from its event log.

The replayer reconstructs a run's step-by-step state purely from the
``run_events`` log — it never calls the model or any tool. It exposes the
ordered timeline and the reconstructed per-step state so a debugger UI/CLI can
step through exactly what happened.

There are two flavours:

* :func:`load_events` / :func:`build_timeline` — pure reconstruction from the
  stored log (no executor involved). This is what the ``/replay`` endpoint
  returns and is provably model-free.
* :func:`replay_with_executor` — drives the real :class:`AgentRunner` with a
  *strict* :class:`ResponseCache` built from the log. Every model/tool call is
  served from the cache; a cache miss raises :class:`CacheMiss`, which is the
  assertion that replay paid nothing. Used to verify the executor reproduces the
  recorded output bit-for-bit.
"""

from __future__ import annotations

from typing import Any

from app.db import get_db
from app.services.timetravel.cache import ResponseCache
from app.services.timetravel.recorder import (
    EVENT_MODEL_CALL,
    EVENT_RUN_END,
    EVENT_STATE,
    EVENT_STEP_BOUNDARY,
    EVENT_TOOL_CALL,
    NullRecorder,
)


def load_events(run_id: str) -> list[dict[str, Any]]:
    """Load a run's full event log ordered by sequence."""
    rows = (
        get_db().table("run_events")
        .select("*")
        .eq("run_id", run_id)
        .order("seq")
        .execute()
    ).data or []
    return list(rows)


def build_timeline(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Reconstruct step-by-step state from an event log without any calls.

    Returns a dict with:
      * ``steps``: list of {step, description, model_responses, tool_calls,
        state} reconstructed in order.
      * ``output``: the final accumulated output (from the last state/run_end).
      * ``total_events``: number of events.
    """
    steps: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    output = ""
    total_tokens = 0

    def _step(n: int) -> dict[str, Any]:
        if n not in steps:
            steps[n] = {
                "step": n,
                "description": "",
                "model_responses": [],
                "tool_calls": [],
                "state": {},
            }
            order.append(n)
        return steps[n]

    for ev in events:
        etype = ev.get("event_type")
        step = int(ev.get("step", 0) or 0)
        payload = ev.get("payload") or {}
        if etype == EVENT_STEP_BOUNDARY:
            _step(step)["description"] = payload.get("description", "")
        elif etype == EVENT_MODEL_CALL:
            _step(step)["model_responses"].append(payload.get("response"))
        elif etype == EVENT_TOOL_CALL:
            _step(step)["tool_calls"].append(
                {"name": payload.get("name"), "args": payload.get("args"), "result": payload.get("result")}
            )
        elif etype == EVENT_STATE:
            _step(step)["state"][payload.get("key")] = payload.get("value")
        elif etype == EVENT_RUN_END:
            output = payload.get("output", output)
            total_tokens = payload.get("total_tokens", total_tokens)

    if not output:
        # Fall back to the last recorded accumulated_context state.
        for n in reversed(order):
            ctx = steps[n]["state"].get("accumulated_context")
            if ctx:
                output = ctx
                break

    return {
        "steps": [steps[n] for n in sorted(order)],
        "output": output,
        "total_tokens": total_tokens,
        "total_events": len(events),
    }


def reconstruct_agent_config(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Rebuild the minimal agent config + input needed to drive the executor.

    Workflow steps come from the recorded ``step_boundary`` events; the user
    input and model come from ``run_start``.
    """
    user_input = ""
    model: str | None = None
    workflow: list[tuple[int, str]] = []
    for ev in events:
        etype = ev.get("event_type")
        payload = ev.get("payload") or {}
        if etype == "run_start":
            user_input = payload.get("user_input", "")
            model = payload.get("model")
        elif etype == EVENT_STEP_BOUNDARY:
            workflow.append((int(ev.get("step", 0) or 0), payload.get("description", "")))
    workflow.sort(key=lambda t: t[0])
    return {
        "agent_config": {
            "system_prompt": "",
            "tools": [],
            "workflow_steps": [d for _s, d in workflow],
            "model": model,
        },
        "user_input": user_input,
    }


async def replay_with_executor(run_id: str) -> dict[str, Any]:
    """Re-drive the executor from the log with a strict cache (zero model calls).

    Returns the reconstructed timeline plus the executor's streamed step outputs.
    Raises :class:`~app.services.timetravel.cache.CacheMiss` if anything would
    have required a real model/tool call.
    """
    from app.services.agent_executor import AgentRunner

    events = load_events(run_id)
    if not events:
        raise ValueError(f"No event log for run {run_id}")

    cache = ResponseCache.from_events(events, strict=True)
    cache.reset_cursors()
    recon = reconstruct_agent_config(events)

    # No recorder (replay must not re-record), strict cache so any real call
    # raises. user_id stays None so no provider is ever constructed.
    runner = AgentRunner(recorder=NullRecorder(), response_cache=cache)

    outputs: list[str] = []
    async for event in runner.execute(
        recon["agent_config"],
        recon["user_input"],
    ):
        if event.get("type") == "token":
            outputs.append(event.get("content", ""))

    timeline = build_timeline(events)
    timeline["replayed_output"] = "".join(outputs)
    return timeline
