"""Eval-driven self-optimization API routes.

Kick off an optimization run (baseline eval → variants → score → gate winner
behind an approval) and read back the lineage.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.routers.auth import get_current_user
from app.services.optimizer import optimizer_service
from app.services.rate_limiter import limiter

router = APIRouter(tags=["optimizer"])


class OptimizationRunRequest(BaseModel):
    agent_id: str
    suite_id: str
    n_variants: int = Field(default=3, ge=1, le=8)
    model: str | None = None


@router.post("/optimizer/runs")
@limiter.limit("5/hour")
async def create_optimization_run(
    request: Request,  # noqa: ARG001 - required by slowapi limiter
    body: OptimizationRunRequest,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Run one self-optimization attempt and return its lineage record."""
    try:
        return await optimizer_service.optimize(
            user_id=user.id,
            agent_id=body.agent_id,
            suite_id=body.suite_id,
            n_variants=body.n_variants,
            model=body.model,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/optimizer/runs")
async def list_optimization_runs(
    agent_id: str | None = Query(default=None),
    user: Any = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    """List a user's optimization runs, newest first."""
    return await optimizer_service.list_lineage(user.id, agent_id=agent_id)


@router.get("/optimizer/runs/{run_id}")
async def get_optimization_run(
    run_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Get an optimization run with its variant lineage."""
    lineage = await optimizer_service.get_lineage(run_id, user.id)
    if not lineage:
        raise HTTPException(status_code=404, detail="Optimization run not found")
    return lineage


@router.post("/optimizer/approvals/{approval_id}/apply")
async def apply_optimization(
    approval_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Promote an approved optimization winner to the agent's active prompt.

    The approval must already be approved (via the approvals API). This records a
    new prompt version and updates the live agent.
    """
    result = await optimizer_service.apply_approved(approval_id=approval_id, user_id=user.id)
    if not result:
        raise HTTPException(
            status_code=400,
            detail="Approval not found, not approved, or not a prompt optimization",
        )
    return result
