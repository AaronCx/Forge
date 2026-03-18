"""Orchestration API routes."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.db import get_db
from app.routers.auth import get_current_user
from app.services.orchestrator import Orchestrator
from app.services.rate_limiter import limiter

router = APIRouter(tags=["orchestration"])


class OrchestrationRequest(BaseModel):
    objective: str = Field(..., min_length=1, max_length=5000)
    tools: list[str] = Field(default_factory=list, max_length=20)


@router.post("/orchestrate")
@limiter.limit("5/hour")
async def start_orchestration(
    body: OrchestrationRequest,
    request: Request,
    user=Depends(get_current_user),  # noqa: B008
):
    """Start an orchestration run. Returns SSE stream of progress."""

    # Create per-request orchestrator with user's provider configs
    user_orchestrator = Orchestrator(user_id=user.id)

    async def event_stream():
        async for event in user_orchestrator.run(
            objective=body.objective,
            user_id=user.id,
            tools=body.tools,
        ):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/orchestrate/groups")
async def list_groups(
    user=Depends(get_current_user),  # noqa: B008
):
    """List all orchestration groups for the user."""
    result = (
        get_db().table("task_groups")
        .select("*")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return result.data or []


@router.get("/orchestrate/groups/{group_id}")
async def get_group(
    group_id: str,
    user=Depends(get_current_user),  # noqa: B008
):
    """Get orchestration group details with members."""
    group = (
        get_db().table("task_groups")
        .select("*")
        .eq("id", group_id)
        .eq("user_id", user.id)
        .single()
        .execute()
    )
    if not group.data:
        raise HTTPException(status_code=404, detail="Group not found")

    members = (
        get_db().table("task_group_members")
        .select("*")
        .eq("group_id", group_id)
        .order("sort_order")
        .execute()
    )

    return {
        **group.data,
        "members": members.data or [],
    }


@router.get("/orchestrate/groups/{group_id}/result")
async def get_group_result(
    group_id: str,
    user=Depends(get_current_user),  # noqa: B008
):
    """Get the final result of an orchestration."""
    group = (
        get_db().table("task_groups")
        .select("id, status, result, objective")
        .eq("id", group_id)
        .eq("user_id", user.id)
        .single()
        .execute()
    )
    if not group.data:
        raise HTTPException(status_code=404, detail="Group not found")

    return group.data
