"""Workflow execution for sessions (Phase 9.5).

Runs a consented plan: compiles the spec, executes the blueprint through the
existing DAG engine, translates engine events into ``WorkflowProgress``-shaped
session events (per stage: running/done agent counts, tokens spent, elapsed),
and persists the outcome into the session log so the model sees the result on
the next turn. Save persists the compiled blueprint to the library with the
spec as metadata — rerunnable, forkable, marketplace-publishable.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.kernel.serialize import workflow_spec_from_dict
from app.kernel.types import WorkflowSpec

logger = logging.getLogger(__name__)

_DEFAULT_CONFIRM_THRESHOLD = 10


def confirm_threshold() -> int:
    """Agent count above which a run requires the explicit confirm flag."""
    try:
        return int(os.getenv("FORGE_WORKFLOW_CONFIRM_THRESHOLD", "") or _DEFAULT_CONFIRM_THRESHOLD)
    except ValueError:
        return _DEFAULT_CONFIRM_THRESHOLD


def get_plan(session_id: str, plan_seq: int) -> dict[str, Any] | None:
    """Fetch a proposed plan's payload from the session event log."""
    from app.services.sessions import get_events

    for ev in get_events(session_id):
        if ev.get("kind") == "workflow_plan" and ev.get("seq") == plan_seq:
            payload = ev.get("payload_json") or {}
            return payload if isinstance(payload, dict) else None
    return None


def _session_compile_args(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session["id"],
        "policy": dict(session.get("policy_json") or {}),
        "workspace_root": session.get("workspace_root", ""),
    }


def save_workflow(
    session: dict[str, Any], spec_dict: dict[str, Any], *, name: str = ""
) -> dict[str, Any]:
    """Persist the compiled workflow to the blueprint library (no agents spawned)."""
    from app.db import get_db
    from app.services.orchestration.compiler import compile_workflow

    spec = workflow_spec_from_dict(spec_dict)
    bp = compile_workflow(
        spec, user_id=session["user_id"], create_agents=False,
        **_session_compile_args(session),
    )
    row = {
        "id": str(uuid.uuid4()),
        "user_id": session["user_id"],
        "name": name or spec.title,
        "description": spec.rationale or f"Saved workflow: {spec.title}",
        "nodes": bp["nodes"],
        "context_config": {"workflow_spec": bp["workflow_spec"]},
        "retry_policy": bp["retry_policy"],
    }
    result = get_db().table("blueprints").insert(row).execute()
    return result.data[0] if result.data else row


async def run_workflow(
    session: dict[str, Any],
    spec_dict: dict[str, Any],
    *,
    goal: str = "",
    plan_seq: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Execute a consented workflow, streaming progress + persisting the outcome."""
    from app.services.blueprint_engine import blueprint_engine
    from app.services.orchestration.compiler import (
        WorkflowCompileError,
        compile_workflow,
    )
    from app.services.orchestration.subagent import (
        disable_mailbox,
        enable_mailbox,
        release_run,
    )
    from app.services.sessions import append_event

    session_id = session["id"]
    user_id = session["user_id"]
    spec: WorkflowSpec = workflow_spec_from_dict(spec_dict)

    try:
        bp = compile_workflow(spec, user_id=user_id, **_session_compile_args(session))
    except WorkflowCompileError as exc:
        yield {"type": "error", "data": f"Workflow failed to compile: {exc}"}
        return

    run_id = f"wf-{uuid.uuid4().hex[:12]}"
    bp["id"] = run_id  # engine uses blueprint id for token accounting

    # Optional inter-agent mailbox (ported from the task_groups Orchestrator):
    # a task_groups row anchors the durable agent_messages log for this run.
    mailbox = False
    try:
        from app.db import get_db

        get_db().table("task_groups").insert({
            "id": run_id, "user_id": user_id,
            "objective": f"Workflow: {spec.title}", "status": "running",
        }).execute()
        enable_mailbox(run_id, run_id, [n["id"] for n in bp["nodes"]])
        mailbox = True
    except Exception:  # noqa: BLE001 - the mailbox is optional
        logger.debug("mailbox unavailable for %s", run_id, exc_info=True)

    node_stage: dict[str, str] = {
        n["id"]: n["config"].get("stage_id", n["id"]) for n in bp["nodes"]
    }
    stages: dict[str, dict[str, int]] = {}
    for node in bp["nodes"]:
        st = stages.setdefault(node_stage[node["id"]], {"total": 0, "done": 0, "running": 0})
        st["total"] += 1

    append_event(session_id, "workflow_run", {
        "run_id": run_id, "plan_seq": plan_seq, "title": spec.title,
        "agents_total": spec.agent_count, "status": "running",
    })
    yield {"type": "workflow_started", "data": {
        "run_id": run_id, "title": spec.title,
        "stages": [{"id": sid, "agents_total": st["total"]} for sid, st in stages.items()],
    }}

    started = time.monotonic()
    tokens_spent = 0
    status = "completed"
    output = ""
    error = ""

    def _progress(stage_id: str) -> dict[str, Any]:
        st = stages[stage_id]
        return {"type": "workflow_progress", "data": {
            "run_id": run_id,
            "stage_id": stage_id,
            "agents_running": st["running"],
            "agents_done": st["done"],
            "agents_total": st["total"],
            "tokens_spent": tokens_spent,
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }}

    try:
        async for ev in blueprint_engine.execute(
            blueprint=bp, input_payload={"text": goal}, user_id=user_id, run_id=run_id,
        ):
            etype = ev.get("type")
            if etype == "layer_start":
                for node_id in ev["data"]["nodes"]:
                    stages[node_stage[node_id]]["running"] += 1
                for stage_id in {node_stage[n] for n in ev["data"]["nodes"]}:
                    yield _progress(stage_id)
            elif etype == "node_done":
                node_id = ev["data"]["node_id"]
                stage_id = node_stage.get(node_id, node_id)
                stages[stage_id]["running"] = max(0, stages[stage_id]["running"] - 1)
                stages[stage_id]["done"] += 1
                tokens_spent += int(ev["data"].get("tokens", 0) or 0)
                yield _progress(stage_id)
            elif etype == "node_error":
                status = "failed"
                error = str(ev["data"].get("error", ""))
                yield {"type": "workflow_error", "data": {
                    "run_id": run_id, "node_id": ev["data"].get("node_id", ""),
                    "error": error,
                }}
            elif etype == "result":
                output = str(ev.get("data", ""))
                tokens_spent = max(tokens_spent, int(ev.get("tokens", 0) or 0))
    except Exception as exc:  # noqa: BLE001 - surface, never hang the stream
        logger.warning("workflow run %s crashed", run_id, exc_info=True)
        status = "failed"
        error = str(exc)
        yield {"type": "workflow_error", "data": {"run_id": run_id, "error": error}}
    finally:
        release_run(run_id)
        if mailbox:
            disable_mailbox(run_id)
            try:
                from app.db import get_db

                get_db().table("task_groups").update(
                    {"status": status}
                ).eq("id", run_id).execute()
            except Exception:  # noqa: BLE001
                logger.debug("task_groups close failed for %s", run_id, exc_info=True)

    done = {
        "run_id": run_id, "plan_seq": plan_seq, "title": spec.title,
        "status": status, "output": output, "error": error,
        "tokens_spent": tokens_spent, "agents_run": spec.agent_count,
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }
    append_event(session_id, "workflow_done", done)
    # A conversation-visible note so the model can use the result next turn.
    note = (
        f"[workflow '{spec.title}' {status}] "
        + (output if status == "completed" else f"error: {error}")
    )
    append_event(session_id, "message", {
        "role": "user", "blocks": [{"kind": "text", "text": note[:20000]}],
    })
    yield {"type": "workflow_done", "data": done}


def list_saved_workflows(user_id: str) -> list[dict[str, Any]]:
    """Blueprints that carry a workflow_spec (saved via Save on a plan card)."""
    from app.db import get_db

    result = (
        get_db().table("blueprints").select("*").eq("user_id", user_id).execute()
    )
    rows = result.data if isinstance(result.data, list) else []
    saved = []
    for row in rows:
        cc = row.get("context_config") or {}
        if isinstance(cc, str):
            try:
                cc = json.loads(cc)
            except (TypeError, ValueError):
                cc = {}
        if isinstance(cc, dict) and cc.get("workflow_spec"):
            saved.append({**row, "workflow_spec": cc["workflow_spec"]})
    return saved
