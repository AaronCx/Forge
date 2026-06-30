"""API routes for organizations and team management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.auth import get_current_user
from app.services.marketplace.org_service import org_service

router = APIRouter(tags=["organizations"])


class CreateOrgRequest(BaseModel):
    name: str
    description: str = ""


class UpdateOrgRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    avatar_url: str | None = None


class AddMemberRequest(BaseModel):
    user_id: str
    role: str = "member"


class UpdateMemberRoleRequest(BaseModel):
    role: str


# === Organizations ===


@router.post("/organizations", status_code=201)
async def create_org(
    body: CreateOrgRequest,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Create a new organization."""
    return await org_service.create_org(
        owner_id=user.id,
        name=body.name,
        description=body.description,
    )


@router.get("/organizations")
async def list_orgs(
    user: Any = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    """List organizations the user belongs to."""
    return await org_service.list_orgs(user.id)


@router.get("/organizations/{org_id}")
async def get_org(
    org_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Get an organization."""
    org = await org_service.get_org(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    # Membership check — the service-role key bypasses RLS, so scope to members.
    role = await org_service.get_user_role(org_id, user.id)
    if role is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.put("/organizations/{org_id}")
async def update_org(
    org_id: str,
    body: UpdateOrgRequest,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Update an organization."""
    updates = body.model_dump(exclude_none=True)
    result = await org_service.update_org(org_id, user.id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Organization not found or not owner")
    return result


@router.delete("/organizations/{org_id}", status_code=204)
async def delete_org(
    org_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
):
    """Delete an organization."""
    deleted = await org_service.delete_org(org_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Organization not found or not owner")


# === Members ===


@router.get("/organizations/{org_id}/members")
async def list_members(
    org_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    """List organization members."""
    role = await org_service.get_user_role(org_id, user.id)
    if not role:
        raise HTTPException(status_code=403, detail="Not a member")
    return await org_service.list_members(org_id)


@router.post("/organizations/{org_id}/members", status_code=201)
async def add_member(
    org_id: str,
    body: AddMemberRequest,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Add a member to an organization (admin+ only)."""
    role = await org_service.get_user_role(org_id, user.id)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return await org_service.add_member(
        org_id=org_id,
        user_id=body.user_id,
        role=body.role,
        invited_by=user.id,
    )


@router.put("/organizations/{org_id}/members/{member_user_id}")
async def update_member_role(
    org_id: str,
    member_user_id: str,
    body: UpdateMemberRoleRequest,
    user: Any = Depends(get_current_user),  # noqa: B008
) -> dict[str, Any]:
    """Update a member's role (admin+ only)."""
    role = await org_service.get_user_role(org_id, user.id)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    # An admin must not be able to demote the org owner.
    if await org_service.get_user_role(org_id, member_user_id) == "owner":
        raise HTTPException(status_code=403, detail="Cannot change the organization owner's role")
    result = await org_service.update_member_role(org_id, member_user_id, body.role)
    if not result:
        raise HTTPException(status_code=404, detail="Member not found or invalid role")
    return result


@router.delete("/organizations/{org_id}/members/{member_user_id}", status_code=204)
async def remove_member(
    org_id: str,
    member_user_id: str,
    user: Any = Depends(get_current_user),  # noqa: B008
):
    """Remove a member from an organization (admin+ only)."""
    role = await org_service.get_user_role(org_id, user.id)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    # An admin must not be able to remove the org owner.
    if await org_service.get_user_role(org_id, member_user_id) == "owner":
        raise HTTPException(status_code=403, detail="Cannot remove the organization owner")
    await org_service.remove_member(org_id, member_user_id)
