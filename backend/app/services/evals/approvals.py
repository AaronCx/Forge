"""Approval service — human-in-the-loop checkpoint management."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.db import get_db

logger = logging.getLogger(__name__)


class ApprovalService:
    """Manages approval gates for blueprint execution."""

    async def create_approval(
        self,
        *,
        user_id: str,
        blueprint_run_id: str,
        node_id: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a pending approval request."""
        approval_id = str(uuid.uuid4())
        row = {
            "id": approval_id,
            "user_id": user_id,
            "blueprint_run_id": blueprint_run_id,
            "node_id": node_id,
            "status": "pending",
            "context": context,
        }
        result = get_db().table("approvals").insert(row).execute()
        return result.data[0] if result.data else row

    async def list_pending(self, user_id: str) -> list[dict[str, Any]]:
        """List all pending approvals for a user."""
        result = (
            get_db().table("approvals")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    async def list_all(self, user_id: str) -> list[dict[str, Any]]:
        """List all approvals for a user (any status)."""
        result = (
            get_db().table("approvals")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    async def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        """Get a single approval by ID."""
        result = (
            get_db().table("approvals")
            .select("*")
            .eq("id", approval_id)
            .single()
            .execute()
        )
        data: dict[str, Any] | None = result.data
        return data

    async def approve(
        self, approval_id: str, user_id: str, feedback: str = ""
    ) -> dict[str, Any] | None:
        """Approve a pending request."""
        approval = await self.get_approval(approval_id)
        if not approval or approval["user_id"] != user_id:
            return None
        if approval["status"] != "pending":
            return None

        result = (
            get_db().table("approvals")
            .update({
                "status": "approved",
                "feedback": feedback,
                "decided_at": datetime.now(UTC).isoformat(),
            })
            .eq("id", approval_id)
            .execute()
        )
        return result.data[0] if result.data else None

    async def reject(
        self, approval_id: str, user_id: str, feedback: str = ""
    ) -> dict[str, Any] | None:
        """Reject a pending request."""
        approval = await self.get_approval(approval_id)
        if not approval or approval["user_id"] != user_id:
            return None
        if approval["status"] != "pending":
            return None

        result = (
            get_db().table("approvals")
            .update({
                "status": "rejected",
                "feedback": feedback,
                "decided_at": datetime.now(UTC).isoformat(),
            })
            .eq("id", approval_id)
            .execute()
        )
        return result.data[0] if result.data else None

    async def get_approval_for_run(
        self, blueprint_run_id: str, node_id: str
    ) -> dict[str, Any] | None:
        """Get the approval status for a specific node in a run."""
        result = (
            get_db().table("approvals")
            .select("*")
            .eq("blueprint_run_id", blueprint_run_id)
            .eq("node_id", node_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data:
            data: dict[str, Any] = result.data[0]
            return data
        return None


approval_service = ApprovalService()
