"""Organization service — manages teams, members, and RBAC."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.db import get_db

logger = logging.getLogger(__name__)


class OrgService:
    """Manages organizations and team membership."""

    # === Organization CRUD ===

    async def create_org(
        self,
        *,
        owner_id: str,
        name: str,
        description: str = "",
    ) -> dict[str, Any]:
        """Create a new organization."""
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        result = get_db().table("organizations").insert({
            "name": name,
            "slug": slug,
            "description": description,
            "owner_id": owner_id,
        }).execute()
        data = result.data
        org: dict[str, Any] = data[0] if isinstance(data, list) else data

        # Add owner as member with 'owner' role
        get_db().table("org_members").insert({
            "org_id": org["id"],
            "user_id": owner_id,
            "role": "owner",
        }).execute()

        return org

    async def list_orgs(self, user_id: str) -> list[dict[str, Any]]:
        """List organizations the user belongs to."""
        memberships = (
            get_db().table("org_members")
            .select("org_id")
            .eq("user_id", user_id)
            .execute()
        ).data or []
        if not memberships:
            return []

        org_ids = [m["org_id"] for m in memberships]
        result = (
            get_db().table("organizations")
            .select("*")
            .in_("id", org_ids)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    async def get_org(self, org_id: str) -> dict[str, Any] | None:
        """Get an organization by ID."""
        result = (
            get_db().table("organizations")
            .select("*")
            .eq("id", org_id)
            .single()
            .execute()
        )
        org: dict[str, Any] | None = result.data
        return org

    async def update_org(
        self, org_id: str, owner_id: str, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update an organization (owner only)."""
        org = await self.get_org(org_id)
        if not org or org["owner_id"] != owner_id:
            return None
        allowed = {k: v for k, v in updates.items() if k in ("name", "description", "avatar_url", "settings")}
        if not allowed:
            return org
        result = (
            get_db().table("organizations")
            .update(allowed)
            .eq("id", org_id)
            .execute()
        )
        data = result.data
        row: dict[str, Any] = data[0] if isinstance(data, list) else data
        return row

    async def delete_org(self, org_id: str, owner_id: str) -> bool:
        """Delete an organization (owner only)."""
        org = await self.get_org(org_id)
        if not org or org["owner_id"] != owner_id:
            return False
        get_db().table("organizations").delete().eq("id", org_id).execute()
        return True

    # === Member management ===

    async def list_members(self, org_id: str) -> list[dict[str, Any]]:
        """List all members of an organization."""
        result = (
            get_db().table("org_members")
            .select("*")
            .eq("org_id", org_id)
            .order("joined_at")
            .execute()
        )
        return result.data or []

    async def add_member(
        self,
        *,
        org_id: str,
        user_id: str,
        role: str = "member",
        invited_by: str | None = None,
    ) -> dict[str, Any]:
        """Add a member to an organization."""
        result = get_db().table("org_members").insert({
            "org_id": org_id,
            "user_id": user_id,
            "role": role,
            "invited_by": invited_by,
        }).execute()
        data = result.data
        member: dict[str, Any] = data[0] if isinstance(data, list) else data
        return member

    async def update_member_role(
        self, org_id: str, user_id: str, role: str
    ) -> dict[str, Any] | None:
        """Update a member's role."""
        if role not in ("admin", "member", "viewer"):
            return None
        result = (
            get_db().table("org_members")
            .update({"role": role})
            .eq("org_id", org_id)
            .eq("user_id", user_id)
            .execute()
        )
        data = result.data
        if not data:
            return None
        row: dict[str, Any] = data[0] if isinstance(data, list) else data
        return row

    async def remove_member(self, org_id: str, user_id: str) -> bool:
        """Remove a member from an organization."""
        get_db().table("org_members").delete().eq(
            "org_id", org_id
        ).eq("user_id", user_id).execute()
        return True

    async def get_user_role(self, org_id: str, user_id: str) -> str | None:
        """Get a user's role in an organization."""
        result = (
            get_db().table("org_members")
            .select("role")
            .eq("org_id", org_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if result.data:
            role_data: dict[str, Any] = result.data
            role: str = role_data["role"]
            return role
        return None


# Global singleton
org_service = OrgService()
