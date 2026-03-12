"""Execution target management endpoints for multi-machine dispatch."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.routers.auth import get_current_user
from app.services.computer_use.dispatch import dispatch_service

router = APIRouter(prefix="/targets", tags=["targets"])


class TargetCreate(BaseModel):
    name: str
    target_type: str = "remote"
    listen_url: str = ""
    api_key: str = ""
    platform: str = "macos"


class TargetUpdate(BaseModel):
    name: str | None = None
    listen_url: str | None = None
    api_key: str | None = None
    platform: str | None = None


@router.get("")
async def list_targets(user: dict = Depends(get_current_user)):
    """List all registered execution targets."""
    return dispatch_service.list_targets()


@router.post("")
async def create_target(body: TargetCreate, user: dict = Depends(get_current_user)):
    """Register a new execution target."""
    import uuid
    target_id = str(uuid.uuid4())
    target = dispatch_service.register_target(
        target_id=target_id,
        name=body.name,
        target_type=body.target_type,
        listen_url=body.listen_url,
        api_key=body.api_key,
        platform=body.platform,
    )
    return {"id": target.id, "name": target.name, "status": target.status}


@router.delete("/{target_id}")
async def remove_target(target_id: str, user: dict = Depends(get_current_user)):
    """Remove an execution target."""
    removed = dispatch_service.remove_target(target_id)
    if not removed:
        return {"error": "Target not found or cannot be removed", "removed": False}
    return {"removed": True}


@router.post("/{target_id}/health")
async def health_check_target(target_id: str, user: dict = Depends(get_current_user)):
    """Run a health check on a specific target."""
    return await dispatch_service.health_check(target_id)


@router.get("/capabilities")
async def aggregated_capabilities(user: dict = Depends(get_current_user)):
    """Aggregated view of capabilities across all targets."""
    targets = dispatch_service.list_targets()
    all_caps: dict = {}
    for t in targets:
        for k, v in t.get("capabilities", {}).items():
            if v:
                all_caps[k] = True
    return {
        "target_count": len(targets),
        "healthy_count": sum(1 for t in targets if t["status"] == "healthy"),
        "capabilities": all_caps,
    }
