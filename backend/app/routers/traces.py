"""API routes for observability traces."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.routers.auth import get_current_user
from app.services.observability.trace_service import trace_service

router = APIRouter(tags=["traces"])


@router.get("/traces")
async def list_traces(
    run_id: str | None = Query(None),
    blueprint_run_id: str | None = Query(None),
    agent_id: str | None = Query(None),
    span_type: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    user: Any = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    """List traces with optional filters."""
    return await trace_service.list_traces(
        user.id,
        run_id=run_id,
        blueprint_run_id=blueprint_run_id,
        agent_id=agent_id,
        span_type=span_type,
        limit=limit,
        offset=offset,
    )


@router.get("/traces/stats")
async def get_trace_stats(
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Get aggregated trace statistics for today."""
    return await trace_service.get_trace_stats(user.id)


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Get a single trace by ID."""
    trace = await trace_service.get_trace(trace_id, user.id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace


@router.get("/traces/{trace_id}/tree")
async def get_trace_tree(
    trace_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Get a trace and its child spans."""
    tree = await trace_service.get_trace_tree(trace_id, user.id)
    if not tree:
        raise HTTPException(status_code=404, detail="Trace not found")
    return tree
