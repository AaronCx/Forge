import contextlib
import json
import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.database import supabase
from app.models.run import RunResponse
from app.routers.auth import get_current_user
from app.services.agent_executor import AgentRunner
from app.services.rate_limiter import limiter

router = APIRouter(tags=["runs"])
agent_runner = AgentRunner()


@router.get("/runs", response_model=list[RunResponse])
async def list_runs(
    user=Depends(get_current_user),  # noqa: B008
):
    result = supabase.table("runs").select("*").eq("user_id", user.id).order("created_at", desc=True).limit(50).execute()
    return result.data


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    user=Depends(get_current_user),  # noqa: B008
):
    result = supabase.table("runs").select("*").eq("id", run_id).single().execute()
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
):
    # Verify token
    try:
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = user_response.user
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    # Get agent config and verify ownership
    agent_result = supabase.table("agents").select("*").eq("id", agent_id).single().execute()
    if not agent_result.data:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_config = agent_result.data
    if agent_config["user_id"] != user.id and not agent_config.get("is_template", False):
        raise HTTPException(status_code=403, detail="Not authorized to run this agent")

    # Create run record
    run_result = supabase.table("runs").insert({
        "agent_id": agent_id,
        "user_id": user.id,
        "input_text": input_text,
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

    async def event_stream():
        step_logs = []
        total_tokens = 0
        final_output = ""
        start_time = time.time()

        try:
            step_num = 0
            async for event in agent_runner.execute(
                agent_config, input_text, heartbeat_id=heartbeat_id,
                run_id=run_id, user_id=user.id,
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
            supabase.table("runs").update({
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

            supabase.table("runs").update({
                "status": "failed",
                "output": str(e),
                "step_logs": step_logs,
            }).eq("id", run_id).execute()

            if heartbeat_id:
                with contextlib.suppress(Exception):
                    heartbeat_service.fail(heartbeat_id)

            yield f"data: {json.dumps({'type': 'error', 'data': 'Agent execution failed. Check run details for more info.'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/stats")
async def get_stats(
    user=Depends(get_current_user),  # noqa: B008
):
    agents = supabase.table("agents").select("id", count="exact").eq("user_id", user.id).execute()  # type: ignore[arg-type]
    runs = supabase.table("runs").select("tokens_used", count="exact").eq("user_id", user.id).execute()  # type: ignore[arg-type]

    total_tokens = sum(r.get("tokens_used", 0) for r in (runs.data or []))

    # Count runs in the last hour
    one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    recent_runs = supabase.table("runs").select("id", count="exact").eq("user_id", user.id).gte("created_at", one_hour_ago).execute()  # type: ignore[arg-type]

    return {
        "total_agents": agents.count or 0,
        "total_runs": runs.count or 0,
        "total_tokens": total_tokens,
        "runs_this_hour": recent_runs.count or 0,
    }
