import contextlib
import json
import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.db import get_db
from app.models.attachment import RunRequest
from app.models.run import RunResponse
from app.routers.auth import get_current_user
from app.services.agent_executor import AgentRunner
from app.services.rate_limiter import limiter

router = APIRouter(tags=["runs"])


class ForkRequest(BaseModel):
    """Body for POST /runs/{id}/fork — rewind to ``from_step`` and apply ``edits``.

    ``edits`` may carry: ``prompt`` (new system prompt), ``user_input`` (new run
    input), ``tool_result`` ({step, value}), and/or ``step_result``
    ({step, content}). The earliest edited step (or ``from_step``) is where real
    recompute begins; everything before it is served from the parent's log.
    """

    from_step: int = Field(ge=1, description="Step to rewind to (1-indexed).")
    edits: dict = Field(default_factory=dict)


@router.get("/runs", response_model=list[RunResponse])
async def list_runs(
    user=Depends(get_current_user),  # noqa: B008
):
    result = get_db().table("runs").select("*").eq("user_id", user.id).order("created_at", desc=True).limit(50).execute()
    return result.data


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    user=Depends(get_current_user),  # noqa: B008
):
    result = get_db().table("runs").select("*").eq("id", run_id).single().execute()
    if not result.data or result.data["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return result.data


@router.post("/agents/{agent_id}/run")
@limiter.limit("10/hour")
async def run_agent(
    agent_id: str,
    request: Request,
    token: str = Query(...),
    input_text: str = Query(""),
    body: RunRequest | None = Body(default=None),  # noqa: B008
):
    # Optional JSON body carries attachments and (optionally) overrides the
    # query-param input_text. Existing CLI/trigger callers POST with no body
    # and are unaffected — the body wins only when present.
    attachments: list[dict] = []
    if body is not None:
        if body.input_text is not None:
            input_text = body.input_text
        attachments = [a.model_dump() for a in body.attachments]

    # Verify token. The auth backend returns either a Supabase-style wrapper
    # (`.user`) or the user object directly (SQLite local auth) — handle both.
    try:
        user_response = get_db().auth.get_user(token)
        user = user_response.user if hasattr(user_response, "user") else user_response
        if not user or not getattr(user, "id", None):
            raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    # Get agent config and verify ownership
    agent_result = get_db().table("agents").select("*").eq("id", agent_id).single().execute()
    if not agent_result.data:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_config = agent_result.data
    if agent_config["user_id"] != user.id and not agent_config.get("is_template", False):
        raise HTTPException(status_code=403, detail="Not authorized to run this agent")

    # Create run record. Persist the first attachment URL for run history;
    # full multimodal context is reconstructed by the runner from attachments.
    first_url = attachments[0]["url"] if attachments else None
    run_result = get_db().table("runs").insert({
        "agent_id": agent_id,
        "user_id": user.id,
        "input_text": input_text,
        "input_file_url": first_url,
        "status": "running",
    }).execute()
    if not run_result.data:
        raise HTTPException(status_code=500, detail="Failed to create run")
    run_id = run_result.data[0]["id"]

    # Create heartbeat for live monitoring
    from app.services.heartbeat import heartbeat_service
    workflow_steps = agent_config.get("workflow_steps", [])
    total_steps = len(workflow_steps) if workflow_steps else 1
    try:
        heartbeat_id = heartbeat_service.start(agent_id, run_id, total_steps)
    except Exception:
        heartbeat_id = None

    # Create a per-request runner with the user's provider configs, plus a
    # recorder so this run is captured in the append-only event log (powers the
    # time-travel debugger: replay + edit-and-fork).
    from app.services.timetravel.recorder import RunRecorder

    agent_runner = AgentRunner(user_id=user.id, recorder=RunRecorder(run_id))

    async def event_stream():
        step_logs = []
        total_tokens = 0
        final_output = ""
        start_time = time.time()

        try:
            step_num = 0
            async for event in agent_runner.execute(
                agent_config, input_text, heartbeat_id=heartbeat_id,
                run_id=run_id, user_id=user.id, attachments=attachments,
            ):
                step_num += 1
                step_start = time.time()

                if event.get("type") == "step":
                    step_log = {
                        "step": step_num,
                        "result": event.get("content", ""),
                        "duration_ms": int((time.time() - step_start) * 1000),
                    }
                    step_logs.append(step_log)
                    yield f"data: {json.dumps({'type': 'step', 'data': step_log})}\n\n"

                elif event.get("type") == "token":
                    yield f"data: {json.dumps({'type': 'token', 'data': event.get('content', '')})}\n\n"
                    final_output += event.get("content", "")

                elif event.get("type") == "tool_call":
                    yield f"data: {json.dumps({'type': 'tool_call', 'data': event})}\n\n"

                total_tokens += event.get("tokens", 0)

            duration_ms = int((time.time() - start_time) * 1000)

            # Update run record
            get_db().table("runs").update({
                "status": "completed",
                "output": final_output,
                "step_logs": step_logs,
                "tokens_used": total_tokens,
                "duration_ms": duration_ms,
            }).eq("id", run_id).execute()

            yield f"data: {json.dumps({'type': 'done', 'run_id': run_id})}\n\n"

        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Agent run %s failed", run_id)

            get_db().table("runs").update({
                "status": "failed",
                "output": str(e),
                "step_logs": step_logs,
            }).eq("id", run_id).execute()

            if heartbeat_id:
                with contextlib.suppress(Exception):
                    heartbeat_service.fail(heartbeat_id)

            yield f"data: {json.dumps({'type': 'error', 'data': 'Agent execution failed. Check run details for more info.'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _assert_run_owner(run_id: str, user_id: str) -> dict:
    """Fetch a run and 404 unless it belongs to ``user_id``."""
    result = get_db().table("runs").select("*").eq("id", run_id).single().execute()
    if not result.data or result.data.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return dict(result.data)


@router.get("/runs/{run_id}/events")
async def get_run_events(
    run_id: str,
    user=Depends(get_current_user),  # noqa: B008
):
    """Return the append-only event log for a run (the time-travel timeline)."""
    from app.services.timetravel import build_timeline, load_events

    _assert_run_owner(run_id, user.id)
    events = load_events(run_id)
    return {
        "run_id": run_id,
        "events": events,
        "timeline": build_timeline(events),
    }


@router.post("/runs/{run_id}/replay")
async def replay_run(
    run_id: str,
    user=Depends(get_current_user),  # noqa: B008
):
    """Deterministically replay a run from its log (zero model/tool calls)."""
    from app.services.timetravel import replay_with_executor

    _assert_run_owner(run_id, user.id)
    try:
        return await replay_with_executor(run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/runs/{run_id}/fork")
@limiter.limit("20/hour")
async def fork_run(
    run_id: str,
    request: Request,  # noqa: ARG001 - required by slowapi limiter
    body: ForkRequest,
    user=Depends(get_current_user),  # noqa: B008
):
    """Edit-and-fork: rewind to a step, apply edits, re-run forward.

    Unchanged steps before the edit are served from the parent's recorded log
    (never re-billed); only the edited step and later steps call the model/tools.
    """
    from app.services.timetravel import fork_service

    _assert_run_owner(run_id, user.id)
    try:
        return await fork_service.fork(
            parent_run_id=run_id,
            user_id=user.id,
            from_step=body.from_step,
            edits=body.edits,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/stats")
async def get_stats(
    user=Depends(get_current_user),  # noqa: B008
):
    agents = get_db().table("agents").select("id", count="exact").eq("user_id", user.id).execute()  # type: ignore[arg-type]
    runs = get_db().table("runs").select("tokens_used", count="exact").eq("user_id", user.id).execute()  # type: ignore[arg-type]

    total_tokens = sum(r.get("tokens_used", 0) for r in (runs.data or []))

    # Count runs in the last hour
    one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    recent_runs = get_db().table("runs").select("id", count="exact").eq("user_id", user.id).gte("created_at", one_hour_ago).execute()  # type: ignore[arg-type]

    return {
        "total_agents": agents.count or 0,
        "total_runs": runs.count or 0,
        "total_tokens": total_tokens,
        "runs_this_hour": recent_runs.count or 0,
    }
