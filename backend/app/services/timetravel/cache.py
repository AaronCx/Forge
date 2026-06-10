"""Step-keyed response cache for replay and edit-and-fork.

This is the mechanism that lets a fork avoid re-paying for unchanged steps. The
cache is built from a parent run's recorded event log: for every ``model_call``
and ``tool_call`` event it stores the recorded response keyed by
``(kind, step, ordinal)`` — ``ordinal`` disambiguates multiple calls of the same
kind within a single step (e.g. a step that makes two tool calls).

During execution the agent runner asks the cache for a response *before* hitting
the provider/tool. On a hit it returns the recorded value and never bills; on a
miss the runner makes the real call. Replay uses a cache in ``strict`` mode where
a miss is a bug (the model must never be called); fork uses a non-strict cache so
edited/downstream steps fall through to real calls.
"""

from __future__ import annotations

from typing import Any

from app.services.timetravel.recorder import EVENT_MODEL_CALL, EVENT_TOOL_CALL


class CacheMiss(Exception):  # noqa: N818 - this is a control-flow signal, not an "error"
    """Raised by a strict cache when a required response wasn't recorded.

    During replay this signals an attempt to invoke the model/tool, which must
    never happen — replay is supposed to be served entirely from the log.
    """


class ResponseCache:
    """Serves recorded model/tool responses keyed by ``(kind, step, ordinal)``."""

    def __init__(self, *, strict: bool = False) -> None:
        # (kind, step, ordinal) -> recorded value
        self._responses: dict[tuple[str, int, int], Any] = {}
        self._strict = strict
        # Per-(kind, step) cursor so repeated calls within a step consume
        # successive recorded responses in order.
        self._cursors: dict[tuple[str, int], int] = {}
        # Steps for which the cache should be authoritative. A call at a step
        # NOT in this set always falls through to a real call (used by fork to
        # invalidate the edited step and everything after it).
        self._served_steps: set[int] | None = None

    @classmethod
    def from_events(
        cls,
        events: list[dict[str, Any]],
        *,
        strict: bool = False,
        max_step: int | None = None,
    ) -> ResponseCache:
        """Build a cache from a list of recorded events.

        Args:
            events: ordered run_events rows (each with ``event_type``, ``step``,
                ``payload``).
            strict: when True, a miss raises :class:`CacheMiss` (replay mode).
            max_step: if given, only events with ``step <= max_step`` are
                loaded — the prefix served on a fork.
        """
        cache = cls(strict=strict)
        for ev in events:
            etype = ev.get("event_type")
            step = int(ev.get("step", 0) or 0)
            if max_step is not None and step > max_step:
                continue
            payload = ev.get("payload") or {}
            if etype == EVENT_MODEL_CALL:
                cache._add("model", step, payload.get("response"))
            elif etype == EVENT_TOOL_CALL:
                cache._add("tool", step, {"name": payload.get("name"), "result": payload.get("result")})
        return cache

    def _add(self, kind: str, step: int, value: Any) -> None:
        ordinal = self._cursors.get((kind, step), 0)
        self._responses[(kind, step, ordinal)] = value
        self._cursors[(kind, step)] = ordinal + 1

    def restrict_to_steps(self, steps: set[int]) -> None:
        """Limit which steps the cache will serve (fork prefix invalidation)."""
        self._served_steps = set(steps)

    def reset_cursors(self) -> None:
        """Reset per-step read cursors so the cache can be consumed for a run."""
        self._cursors = {}

    def _next(self, kind: str, step: int) -> tuple[bool, Any]:
        """Return (hit, value) for the next response of ``kind`` at ``step``."""
        if self._served_steps is not None and step not in self._served_steps:
            return False, None
        ordinal = self._cursors.get((kind, step), 0)
        key = (kind, step, ordinal)
        if key in self._responses:
            self._cursors[(kind, step)] = ordinal + 1
            return True, self._responses[key]
        if self._strict:
            raise CacheMiss(
                f"No recorded {kind} response for step {step} (ordinal {ordinal}); "
                "replay must be fully served from the event log."
            )
        return False, None

    def get_model(self, step: int) -> tuple[bool, Any]:
        """Get the next recorded model response for a step, if cached."""
        return self._next("model", step)

    def get_tool(self, step: int) -> tuple[bool, Any]:
        """Get the next recorded tool response for a step, if cached."""
        return self._next("tool", step)

    def has_step(self, step: int) -> bool:
        """True if any model/tool response is cached for ``step``."""
        return any(s == step for (_k, s, _o) in self._responses)
