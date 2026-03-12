"""Cost and token usage API routes."""

from fastapi import APIRouter, Depends, Query

from app.routers.auth import get_current_user
from app.services.token_tracker import token_tracker

router = APIRouter(tags=["costs"])


@router.get("/costs/summary")
async def cost_summary(
    user=Depends(get_current_user),  # noqa: B008
    period: str = Query("today", regex="^(today|week|month)$"),
):
    """Get cost summary for a period."""
    return token_tracker.get_summary(user.id, period)


@router.get("/costs/breakdown")
async def cost_breakdown(
    user=Depends(get_current_user),  # noqa: B008
    group_by: str = Query("agent", regex="^(agent|model)$"),
):
    """Get cost breakdown by agent or model."""
    return token_tracker.get_breakdown(user.id, group_by)


@router.get("/costs/run/{run_id}")
async def run_usage(
    run_id: str,
    user=Depends(get_current_user),  # noqa: B008
):
    """Get step-by-step token usage for a run."""
    return token_tracker.get_run_usage(run_id)


@router.get("/costs/projection")
async def cost_projection(
    user=Depends(get_current_user),  # noqa: B008
):
    """Get monthly cost projection based on recent usage."""
    return token_tracker.get_projection(user.id)


@router.get("/costs/all")
async def all_cost_data(
    user=Depends(get_current_user),  # noqa: B008
):
    """Get all cost data in a single request (summary + breakdown + projection)."""
    return {
        "today": token_tracker.get_summary(user.id, "today"),
        "week": token_tracker.get_summary(user.id, "week"),
        "month": token_tracker.get_summary(user.id, "month"),
        "by_agent": token_tracker.get_breakdown(user.id, "agent"),
        "by_model": token_tracker.get_breakdown(user.id, "model"),
        "projection": token_tracker.get_projection(user.id),
    }
