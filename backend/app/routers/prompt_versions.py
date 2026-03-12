"""API routes for prompt versioning."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.auth import get_current_user
from app.services.observability.prompt_versions import prompt_version_service

router = APIRouter(tags=["prompt_versions"])


class CreateVersionRequest(BaseModel):
    system_prompt: str
    change_summary: str = ""


@router.get("/agents/{agent_id}/prompts")
async def list_prompt_versions(
    agent_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    """List all prompt versions for an agent."""
    return await prompt_version_service.list_versions(agent_id, user.id)


@router.get("/agents/{agent_id}/prompts/active")
async def get_active_version(
    agent_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Get the active prompt version for an agent."""
    version = await prompt_version_service.get_active_version(agent_id, user.id)
    if not version:
        raise HTTPException(status_code=404, detail="No prompt versions found")
    return version


@router.post("/agents/{agent_id}/prompts")
async def create_prompt_version(
    agent_id: str,
    body: CreateVersionRequest,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Create a new prompt version for an agent."""
    version = await prompt_version_service.create_version(
        user_id=user.id,
        agent_id=agent_id,
        system_prompt=body.system_prompt,
        change_summary=body.change_summary,
    )
    return version


@router.get("/prompts/{version_id}")
async def get_prompt_version(
    version_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Get a specific prompt version with full text."""
    version = await prompt_version_service.get_version(version_id, user.id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return version


@router.post("/prompts/{version_id}/rollback")
async def rollback_prompt(
    version_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Rollback to a specific prompt version."""
    result = await prompt_version_service.rollback(version_id, user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Version not found")
    return result


@router.get("/prompts/{version_a}/diff/{version_b}")
async def diff_versions(
    version_a: str,
    version_b: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Compare two prompt versions."""
    result = await prompt_version_service.diff_versions(version_a, version_b, user.id)
    if not result:
        raise HTTPException(status_code=404, detail="One or both versions not found")
    return result
