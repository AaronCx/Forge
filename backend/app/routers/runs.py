import json
import time
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from app.routers.auth import get_current_user
from app.models.run import RunResponse
from app.database import supabase
from app.services.rate_limiter import limiter
from app.services.agent_executor import AgentRunner

router = APIRouter(tags=["runs"])
agent_runner = AgentRunner()


@router.get("/runs", response_model=list[RunResponse])
async def list_runs(user=Depends(get_current_user)):
    result = supabase.table("runs").select("*").eq("user_id", user.id).order("created_at", desc=True).limit(50).execute()
    return result.data


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, user=Depends(get_current_user)):
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
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Get agent config
    agent_result = supabase.table("agents").select("*").eq("id", agent_id).single().execute()
    if not agent_result.data:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_config = agent_result.data

    # Create run record
    run_result = supabase.table("runs").insert({
        "agent_id": agent_id,
        "user_id": user.id,
        "input_text": input_text,
        "status": "running",
    }).execute()
    run_id = run_result.data[0]["id"]

    async def event_stream():
        step_logs = []
        total_tokens = 0
        final_output = ""
        start_time = time.time()

        try:
            step_num = 0
            async for event in agent_runner.execute(agent_config, input_text):
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
            supabase.table("runs").update({
                "status": "failed",
                "output": str(e),
                "step_logs": step_logs,
            }).eq("id", run_id).execute()

            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/stats")
async def get_stats(user=Depends(get_current_user)):
    agents = supabase.table("agents").select("id", count="exact").eq("user_id", user.id).execute()
    runs = supabase.table("runs").select("tokens_used", count="exact").eq("user_id", user.id).execute()

    total_tokens = sum(r.get("tokens_used", 0) for r in (runs.data or []))

    # Count runs in the last hour
    from datetime import datetime, timedelta, timezone
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    recent_runs = supabase.table("runs").select("id", count="exact").eq("user_id", user.id).gte("created_at", one_hour_ago).execute()

    return {
        "total_agents": agents.count or 0,
        "total_runs": runs.count or 0,
        "total_tokens": total_tokens,
        "runs_this_hour": recent_runs.count or 0,
    }
