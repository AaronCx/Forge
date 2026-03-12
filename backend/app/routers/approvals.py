"""Approval management API routes — human-in-the-loop."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.auth import get_current_user
from app.services.evals.approvals import approval_service

router = APIRouter(tags=["approvals"])


class ApprovalDecision(BaseModel):
    feedback: str = ""


@router.get("/approvals")
async def list_approvals(
    status: str = "pending",
    user: Any = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    """List approvals. Default: pending only."""
    if status == "all":
        return await approval_service.list_all(user.id)
    return await approval_service.list_pending(user.id)


@router.get("/approvals/{approval_id}")
async def get_approval(
    approval_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Get a single approval."""
    approval = await approval_service.get_approval(approval_id)
    if not approval or approval["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


@router.post("/approvals/{approval_id}/approve")
async def approve(
    approval_id: str,
    req: ApprovalDecision | None = None,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Approve a pending request."""
    feedback = req.feedback if req else ""
    result = await approval_service.approve(approval_id, user.id, feedback)
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found or already decided")
    return result


@router.post("/approvals/{approval_id}/reject")
async def reject(
    approval_id: str,
    req: ApprovalDecision | None = None,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Reject a pending request."""
    feedback = req.feedback if req else ""
    result = await approval_service.reject(approval_id, user.id, feedback)
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found or already decided")
    return result
