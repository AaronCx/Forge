"""Append-only event recorder for agent runs (the time-travel debugger's log).

A :class:`RunRecorder` is a thin sink the agent executor notifies at each model
call, tool call, state mutation, and step boundary. It assigns a monotonic
``seq`` and persists every event through the existing dual-backend ``get_db()``
so the SQLite and Supabase stores share one code path.

The recorder is deliberately dumb: it only *appends*. Reconstruction (replay)
and prefix-copying (fork) live in :mod:`app.services.timetravel.replayer` and
:mod:`app.services.timetravel.fork` so the hot execution path stays clean.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.db import get_db

logger = logging.getLogger(__name__)

# Event types written to the run_events log. Kept in sync with the CHECK
# constraint in both the SQLite schema and the Supabase migration.
EVENT_RUN_START = "run_start"
EVENT_STEP_BOUNDARY = "step_boundary"
EVENT_MODEL_CALL = "model_call"
EVENT_TOOL_CALL = "tool_call"
EVENT_STATE = "state"
EVENT_RUN_END = "run_end"


class RunRecorder:
    """Append-only sink that persists a run's event log.

    One recorder instance is created per run. It is safe to disable (``enabled``
    False) so the executor can be driven during replay without re-recording, and
    so callers that don't want a log pay nothing.
    """

    def __init__(self, run_id: str, *, enabled: bool = True) -> None:
        self.run_id = run_id
        self.enabled = enabled
        self._seq = 0

    def _append(self, event_type: str, step: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist one event and return the stored row (best-effort)."""
        seq = self._seq
        self._seq += 1
        row = {
            "id": str(uuid.uuid4()),
            "run_id": self.run_id,
            "seq": seq,
            "step": step,
            "event_type": event_type,
            "payload": payload,
        }
        if not self.enabled:
            return row
        try:
            get_db().table("run_events").insert(row).execute()
        except Exception:
            # Recording must never break a run. A lost event degrades replay
            # fidelity but the run itself completes.
            logger.warning("Failed to record run event %s for run %s", event_type, self.run_id, exc_info=True)
        return row

    def run_start(self, *, agent_id: str | None, user_input: str, model: str | None) -> None:
        self._append(EVENT_RUN_START, 0, {
            "agent_id": agent_id,
            "user_input": user_input,
            "model": model,
        })

    def step_boundary(self, step: int, description: str) -> None:
        self._append(EVENT_STEP_BOUNDARY, step, {"description": description})

    def model_call(self, step: int, *, request: dict[str, Any], response: dict[str, Any]) -> None:
        """Record a model call: the full request and the provider response."""
        self._append(EVENT_MODEL_CALL, step, {"request": request, "response": response})

    def tool_call(self, step: int, *, name: str, args: dict[str, Any], result: Any) -> None:
        """Record a tool invocation: tool name, arguments, and its result."""
        self._append(EVENT_TOOL_CALL, step, {"name": name, "args": args, "result": result})

    def state(self, step: int, *, key: str, value: Any) -> None:
        """Record a state mutation (e.g. accumulated context after a step)."""
        self._append(EVENT_STATE, step, {"key": key, "value": value})

    def run_end(self, *, status: str, output: str, total_tokens: int) -> None:
        self._append(EVENT_RUN_END, 0, {
            "status": status,
            "output": output,
            "total_tokens": total_tokens,
        })


# A no-op recorder used when recording is disabled (e.g. during replay). Every
# method is a no-op; the executor calls it unconditionally so there are no
# `if recorder:` branches on the hot path.
class NullRecorder(RunRecorder):
    """Recorder that drops everything — used when recording is turned off."""

    def __init__(self) -> None:
        super().__init__(run_id="", enabled=False)

    def _append(self, event_type: str, step: int, payload: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        return {}
