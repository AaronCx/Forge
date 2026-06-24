"""Edit-and-fork: rewind a run to step N, change something, re-run forward.

The killer feature of the time-travel debugger. A fork:

1. Loads the parent run's event log and reconstructs its agent config + input.
2. Creates a brand-new child run row.
3. Copies the parent's event-log prefix (events at step ``< from_step``) into the
   child's log verbatim.
4. Builds a step-keyed :class:`ResponseCache` from that same prefix and
   *restricts it to the unchanged steps* (``< from_step``). When the executor
   re-runs, every step before the edit is served from this cache — so those
   steps are never re-billed. The edited step (``from_step``) and everything
   after it miss the cache and make real model/tool calls.
5. Applies the edits (modified prompt and/or a modified tool/step result that is
   injected into the cache so the recompute downstream sees the new value).
6. Resumes the :class:`AgentRunner` forward with a fresh recorder so the child's
   log captures the re-run from ``from_step`` onward.

Edits shape (all optional)::

    {
        "prompt": "new system prompt text",       # replaces system_prompt
        "user_input": "new user input",            # replaces the run input
        "tool_result": {"step": N, "value": ...},  # override a recorded tool result
        "step_result": {"step": N, "content": ...} # override a step's model output
    }

The earliest edited step determines where real recompute begins; ``from_step`` is
used when no per-step edit is earlier.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.db import get_db
from app.services.timetravel.cache import ResponseCache
from app.services.timetravel.recorder import RunRecorder
from app.services.timetravel.replayer import load_events, reconstruct_agent_config

logger = logging.getLogger(__name__)


class ForkService:
    """Creates a forked run from a parent run at step N with edits."""

    async def fork(
        self,
        *,
        parent_run_id: str,
        user_id: str,
        from_step: int,
        edits: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Fork a run at ``from_step`` and re-run forward, reusing the prefix.

        Returns the lineage record for the new child run (including its id and
        which steps were served from cache vs. recomputed).
        """
        edits = edits or {}

        parent = (
            get_db().table("runs").select("*").eq("id", parent_run_id).single().execute()
        ).data
        if not parent or parent.get("user_id") != user_id:
            raise ValueError("Parent run not found")

        events = load_events(parent_run_id)
        if not events:
            raise ValueError(f"Parent run {parent_run_id} has no recorded event log")

        recon = reconstruct_agent_config(events)
        agent_config = recon["agent_config"]
        user_input = recon["user_input"]

        # Pull the parent agent's real config (system prompt + tools) — the event
        # log records workflow/model but the system prompt lives on the agent.
        parent_agent_id = parent.get("agent_id")
        if parent_agent_id:
            agent = (
                get_db().table("agents").select("*").eq("id", parent_agent_id).single().execute()
            ).data
            if agent:
                agent_config = {
                    **agent_config,
                    "id": agent.get("id"),
                    "name": agent.get("name"),
                    "system_prompt": agent.get("system_prompt", ""),
                    "tools": agent.get("tools", []),
                    "model": agent_config.get("model") or agent.get("model"),
                }

        # --- Apply edits ---------------------------------------------------
        # An edit at step K invalidates step K and everything after it. The
        # cut-over (first recomputed step) is the min of from_step and any
        # per-step edit's step.
        cut_step = from_step
        if "prompt" in edits:
            agent_config = {**agent_config, "system_prompt": edits["prompt"]}
            # A prompt change invalidates the whole run.
            cut_step = 1
        if "user_input" in edits:
            user_input = edits["user_input"]
            cut_step = 1

        tool_override = edits.get("tool_result")
        if isinstance(tool_override, dict) and "step" in tool_override:
            cut_step = min(cut_step, int(tool_override["step"]))
        step_override = edits.get("step_result")
        if isinstance(step_override, dict) and "step" in step_override:
            cut_step = min(cut_step, int(step_override["step"]))

        cut_step = max(1, cut_step)

        # --- Create the child run row -------------------------------------
        child_run_id = str(uuid.uuid4())
        get_db().table("runs").insert({
            "id": child_run_id,
            "agent_id": parent_agent_id,
            "user_id": user_id,
            "input_text": user_input,
            "status": "running",
        }).execute()

        # --- Copy the unchanged prefix into the child's log ---------------
        # Events for steps strictly before cut_step are copied verbatim so the
        # child's log is a true continuation. run_start is re-emitted by the
        # executor, so we copy step_boundary/model_call/tool_call/state for the
        # prefix steps only.
        copied = self._copy_prefix(events, child_run_id, cut_step)

        # --- Build the prefix cache (served, not re-billed) ---------------
        cache = ResponseCache.from_events(events, max_step=cut_step - 1)
        cache.restrict_to_steps(set(range(1, cut_step)))
        cache.reset_cursors()

        # Inject any tool/step result override so downstream recompute sees the
        # edited value. (Only meaningful when the override step is < cut_step,
        # i.e. the user pinned an earlier step's result and asked to recompute
        # from there — the override seeds the served prefix.)
        self._apply_result_overrides(cache, edits)

        # Report the steps ACTUALLY served from cache, not the whole prefix range.
        # A prefix step whose model_call event was lost (recorder swallows insert
        # failures) isn't in the cache → it gets recomputed and re-billed, so it
        # must not be reported as served (the old range(1, cut_step) silently
        # over-reported cache hits / under-reported re-billing).
        served_steps = sorted({
            step for (kind, step, _ordinal) in cache._responses
            if kind == "model" and step < cut_step
        })

        # --- Resume the executor forward ----------------------------------
        from app.services.agent_executor import AgentRunner

        recorder = RunRecorder(child_run_id)
        # Re-seed the recorder's seq past the copied prefix so the child log
        # stays monotonic.
        recorder._seq = copied  # noqa: SLF001 - intentional continuation of the log

        runner = AgentRunner(user_id=user_id, recorder=recorder, response_cache=cache)

        final_output = ""
        total_tokens = 0
        recomputed_steps: list[int] = []
        try:
            async for event in runner.execute(agent_config, user_input, run_id=child_run_id, user_id=user_id):
                if event.get("type") == "token":
                    final_output += event.get("content", "")
                total_tokens += event.get("tokens", 0)
            # Steps at/after the cut were recomputed (not served).
            recomputed_steps = [
                s for s in range(1, len(agent_config.get("workflow_steps", [])) + 1) if s >= cut_step
            ]
            get_db().table("runs").update({
                "status": "completed",
                "output": final_output,
                "tokens_used": total_tokens,
            }).eq("id", child_run_id).execute()
        except Exception as e:
            logger.exception("Fork of run %s failed", parent_run_id)
            get_db().table("runs").update({
                "status": "failed",
                "output": str(e),
            }).eq("id", child_run_id).execute()
            raise

        # --- Record lineage ------------------------------------------------
        fork_id = str(uuid.uuid4())
        get_db().table("run_forks").insert({
            "id": fork_id,
            "parent_run_id": parent_run_id,
            "child_run_id": child_run_id,
            "user_id": user_id,
            "from_step": cut_step,
            "edits": edits,
        }).execute()

        return {
            "fork_id": fork_id,
            "parent_run_id": parent_run_id,
            "child_run_id": child_run_id,
            "from_step": cut_step,
            "served_from_cache_steps": served_steps,
            "recomputed_steps": recomputed_steps,
            "edits": edits,
            "output": final_output,
        }

    @staticmethod
    def _copy_prefix(events: list[dict[str, Any]], child_run_id: str, cut_step: int) -> int:
        """Copy prefix events (step < cut_step) into the child's log.

        Returns the number of events copied (= the seq to resume from).
        """
        copied = 0
        for ev in events:
            etype = ev.get("event_type")
            step = int(ev.get("step", 0) or 0)
            # run_start/run_end are re-emitted by the new run; only carry the
            # per-step prefix forward.
            if etype in ("run_start", "run_end"):
                continue
            if step >= cut_step or step < 1:
                continue
            get_db().table("run_events").insert({
                "id": str(uuid.uuid4()),
                "run_id": child_run_id,
                "seq": copied,
                "step": step,
                "event_type": etype,
                "payload": ev.get("payload") or {},
            }).execute()
            copied += 1
        return copied

    @staticmethod
    def _apply_result_overrides(cache: ResponseCache, edits: dict[str, Any]) -> None:
        """Inject edited tool/step results into the served prefix cache."""
        step_override = edits.get("step_result")
        if isinstance(step_override, dict) and "step" in step_override:
            step = int(step_override["step"])
            # Replace the served model response for that step.
            cache._responses[("model", step, 0)] = {  # noqa: SLF001
                "content": step_override.get("content", ""),
                "tokens": 0,
            }
        tool_override = edits.get("tool_result")
        if isinstance(tool_override, dict) and "step" in tool_override:
            step = int(tool_override["step"])
            key = ("tool", step, 0)
            existing = cache._responses.get(key, {})  # noqa: SLF001
            name = existing.get("name") if isinstance(existing, dict) else None
            cache._responses[key] = {"name": name, "result": tool_override.get("value")}  # noqa: SLF001


fork_service = ForkService()
