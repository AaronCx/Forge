"""Dashboard API routes for live monitoring."""

import asyncio
import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.routers.auth import get_current_user
from app.database import supabase
from app.services.heartbeat import heartbeat_service

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/active")
async def get_active_agents(user=Depends(get_current_user)):
    """Get all active agent heartbeats with agent details."""
    heartbeats = heartbeat_service.get_active()
    return heartbeats


@router.get("/dashboard/metrics")
async def get_dashboard_metrics(user=Depends(get_current_user)):
    """Get aggregate dashboard metrics."""
    metrics = heartbeat_service.get_metrics()
    return metrics


@router.get("/dashboard/timeline")
async def get_event_timeline(
    user=Depends(get_current_user),
    limit: int = 50,
    agent_id: str | None = None,
):
    """Get recent agent events for the timeline."""
    query = (
        supabase.table("agent_heartbeats")
        .select("*, agents(name)")
        .order("updated_at", desc=True)
        .limit(limit)
    )

    if agent_id:
        query = query.eq("agent_id", agent_id)

    result = query.execute()

    events = []
    for hb in (result.data or []):
        agent_name = hb.get("agents", {}).get("name", "Unknown") if hb.get("agents") else "Unknown"
        severity = "info"
        if hb["state"] == "failed":
            severity = "error"
        elif hb["state"] == "stalled":
            severity = "warning"
        elif hb["state"] == "completed":
            severity = "success"

        events.append({
            "id": hb["id"],
            "agent_id": hb["agent_id"],
            "agent_name": agent_name,
            "run_id": hb.get("run_id"),
            "state": hb["state"],
            "severity": severity,
            "current_step": hb["current_step"],
            "total_steps": hb["total_steps"],
            "tokens_used": hb["tokens_used"],
            "cost_estimate": float(hb.get("cost_estimate", 0)),
            "output_preview": hb.get("output_preview", ""),
            "updated_at": hb["updated_at"],
        })

    return events


@router.get("/dashboard/stream")
async def stream_dashboard_updates(
    request: Request,
    token: str = "",
):
    """SSE stream for real-time dashboard updates."""
    # Verify token
    if token:
        try:
            user_response = supabase.auth.get_user(token)
            if not user_response or not user_response.user:
                return {"error": "Invalid token"}
        except Exception:
            return {"error": "Invalid token"}

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break

            # Detect stalled agents
            heartbeat_service.detect_stalled()

            # Get current state
            active = heartbeat_service.get_active()
            metrics = heartbeat_service.get_metrics()

            payload = {
                "active_agents": active,
                "metrics": metrics,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            yield f"data: {json.dumps(payload, default=str)}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/dashboard/health")
async def dashboard_health():
    """Health check for the dashboard service."""
    return {
        "status": "ok",
        "service": "dashboard",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
