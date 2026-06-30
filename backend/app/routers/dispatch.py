"""Dispatch endpoint — route a message to an agent/blueprint and stream it back.

POST /api/dispatch (SSE). The dispatcher decides a target, then the chosen run
is executed through the same services the normal run endpoints use, so a
heartbeat is created and the dashboard's live metrics refresh automatically.
Event types: routing | step | token | clarify | none | done | error.
"""

import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.db import get_db
from app.models.dispatch import CatalogEntry, DispatchRequest
from app.routers.auth import get_current_user
from app.services import dispatcher
from app.services.agent_executor import AgentRunner
from app.services.rate_limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dispatch"])


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _resolve_user(token: str):
    """Verify a query-param token (dual Supabase/SQLite unwrap)."""
    try:
        user_response = get_db().auth.get_user(token)
        user = user_response.user if hasattr(user_response, "user") else user_response
        if not user or not getattr(user, "id", None):
            raise HTTPException(status_code=401, detail="Invalid token")
        return user
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


@router.get("/dispatch/targets", response_model=list[CatalogEntry])
async def list_targets(user=Depends(get_current_user)):  # noqa: B008
    """The user's agents + blueprints, for the composer's target-override picker."""
    return dispatcher.build_catalog(user.id)


@router.post("/dispatch")
@limiter.limit("20/hour")
async def dispatch(
    request: Request,
    body: DispatchRequest,
    token: str = Query(...),
):
    """Route a message and stream the resulting run back over SSE."""
    user = _resolve_user(token)
    user_id = user.id
    attachments = [a.model_dump() for a in body.attachments]

    async def event_stream() -> AsyncIterator[str]:
        try:
            # PR-7: an explicit override skips routing entirely.
            if body.target_type and body.target_id:
                from app.models.dispatch import Decision

                decision = Decision(
                    action="route",
                    target_type=body.target_type,
                    target_id=body.target_id,
                    input_text=body.message,
                    rationale="Target chosen by user.",
                )
            else:
                # PR-5: let routing see attachment names + document previews.
                attachments_summary = await dispatcher.build_attachments_summary(attachments)
                decision = await dispatcher.route(user_id, body.message, attachments_summary)

            if decision.action == "clarify":
                yield _sse({"type": "clarify", "question": decision.clarifying_question, "thread_id": body.thread_id})
                return
            if decision.action == "none":
                yield _sse({
                    "type": "none",
                    "message": decision.rationale or "No matching agent/blueprint.",
                    "cold_start": decision.cold_start,
                })
                return

            # action == "route"
            target_id = decision.target_id
            if not target_id:
                yield _sse({"type": "none", "message": "No matching agent/blueprint.", "cold_start": False})
                return

            yield _sse({
                "type": "routing",
                "target": {"type": decision.target_type, "id": target_id},
                "rationale": decision.rationale,
                "routing_cost": decision.routing_cost,
            })

            run_input = decision.input_text or body.message
            if decision.target_type == "blueprint":
                async for ev in _run_blueprint(user_id, target_id, run_input, attachments):
                    yield ev
            else:
                async for ev in _run_agent(user_id, target_id, run_input, attachments):
                    yield ev

        except Exception:
            logger.exception("Dispatch failed for user %s", user_id)
            yield _sse({"type": "error", "data": "Dispatch failed. Check server logs for details."})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _run_agent(
    user_id: str, agent_id: str, input_text: str, attachments: list[dict]
) -> AsyncIterator[str]:
    """Run an agent through the normal run services and relay SSE events."""
    from app.services.heartbeat import heartbeat_service

    agent_result = get_db().table("agents").select("*").eq("id", agent_id).single().execute()
    if not agent_result.data:
        yield _sse({"type": "error", "data": "Routed agent not found."})
        return
    agent_config = agent_result.data
    # Ownership check — the override path bypasses routing, so enforce here that
    # the caller owns the agent (or it's a shared template). Mirrors runs.py:88.
    if agent_config.get("user_id") != user_id and not agent_config.get("is_template"):
        yield _sse({"type": "error", "data": "Routed agent not found."})
        return

    first_url = attachments[0]["url"] if attachments else None
    run_result = get_db().table("runs").insert({
        "agent_id": agent_id,
        "user_id": user_id,
        "input_text": input_text,
        "input_file_url": first_url,
        "status": "running",
    }).execute()
    if not run_result.data:
        yield _sse({"type": "error", "data": "Failed to create run."})
        return
    run_id = run_result.data[0]["id"]

    workflow_steps = agent_config.get("workflow_steps", [])
    total_steps = len(workflow_steps) if workflow_steps else 1
    try:
        heartbeat_id = heartbeat_service.start(agent_id, run_id, total_steps)
    except Exception:
        heartbeat_id = None

    runner = AgentRunner(user_id=user_id)
    step_logs: list[dict] = []
    final_output = ""
    start_time = time.time()
    step_num = 0

    try:
        async for event in runner.execute(
            agent_config, input_text, heartbeat_id=heartbeat_id,
            run_id=run_id, user_id=user_id, attachments=attachments,
        ):
            etype = event.get("type")
            if etype == "step":
                step_num += 1
                log = {"step": step_num, "result": event.get("content", ""), "duration_ms": 0}
                step_logs.append(log)
                yield _sse({"type": "step", "data": log})
            elif etype == "token":
                final_output += event.get("content", "")
                yield _sse({"type": "token", "data": event.get("content", "")})

        get_db().table("runs").update({
            "status": "completed",
            "output": final_output,
            "step_logs": step_logs,
            "duration_ms": int((time.time() - start_time) * 1000),
        }).eq("id", run_id).execute()

        yield _sse({"type": "done", "run_id": run_id})

    except Exception:
        logger.exception("Dispatched agent run %s failed", run_id)
        get_db().table("runs").update({"status": "failed", "step_logs": step_logs}).eq("id", run_id).execute()
        if heartbeat_id:
            with contextlib.suppress(Exception):
                heartbeat_service.fail(heartbeat_id)
        yield _sse({"type": "error", "data": "Agent execution failed."})


async def _run_blueprint(
    user_id: str, blueprint_id: str, input_text: str, attachments: list[dict]
) -> AsyncIterator[str]:
    """Run a blueprint through the blueprint engine and relay SSE events."""
    from app.services.blueprint_engine import blueprint_engine

    bp_result = get_db().table("blueprints").select("*").eq("id", blueprint_id).single().execute()
    if not bp_result.data:
        yield _sse({"type": "error", "data": "Routed blueprint not found."})
        return
    blueprint = bp_result.data
    # Ownership check — the override path bypasses routing. Mirrors blueprints.py:184.
    if blueprint.get("user_id") != user_id and not blueprint.get("is_template"):
        yield _sse({"type": "error", "data": "Routed blueprint not found."})
        return

    input_payload: dict = {"text": input_text}
    if attachments:
        input_payload["attachments"] = attachments

    run_result = get_db().table("blueprint_runs").insert({
        "blueprint_id": blueprint_id,
        "user_id": user_id,
        "status": "running",
        "input_payload": input_payload,
        "started_at": "now()",
    }).execute()
    if not run_result.data:
        yield _sse({"type": "error", "data": "Failed to create blueprint run."})
        return
    run_id = run_result.data[0]["id"]

    try:
        async for event in blueprint_engine.execute(
            blueprint=blueprint, input_payload=input_payload, user_id=user_id, run_id=run_id,
        ):
            yield _sse({"type": "step", "data": event})
        yield _sse({"type": "done", "run_id": run_id})
    except Exception:
        logger.exception("Dispatched blueprint run %s failed", run_id)
        get_db().table("blueprint_runs").update({"status": "failed"}).eq("id", run_id).execute()
        yield _sse({"type": "error", "data": "Blueprint execution failed."})
