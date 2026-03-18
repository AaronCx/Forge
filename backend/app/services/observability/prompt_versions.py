"""Prompt versioning service — tracks system prompt changes with diffs."""

from __future__ import annotations

import difflib
import logging
from typing import Any

from app.db import get_db

logger = logging.getLogger(__name__)


class PromptVersionService:
    """Manages prompt version history for agents."""

    async def create_version(
        self,
        *,
        user_id: str,
        agent_id: str,
        system_prompt: str,
        change_summary: str = "",
    ) -> dict[str, Any]:
        """Create a new prompt version, computing diff from previous."""
        # Get the current active version
        prev = (
            get_db().table("prompt_versions")
            .select("*")
            .eq("agent_id", agent_id)
            .eq("is_active", True)
            .order("version_number", desc=True)
            .limit(1)
            .execute()
        ).data

        previous_prompt = ""
        next_version = 1

        if prev:
            previous_prompt = prev[0].get("system_prompt", "")
            next_version = prev[0].get("version_number", 0) + 1
            # Deactivate previous version
            get_db().table("prompt_versions").update(
                {"is_active": False}
            ).eq("id", prev[0]["id"]).execute()

        # Compute diff
        diff = self._compute_diff(previous_prompt, system_prompt)

        row = {
            "user_id": user_id,
            "agent_id": agent_id,
            "version_number": next_version,
            "system_prompt": system_prompt,
            "change_summary": change_summary or f"Version {next_version}",
            "diff_from_previous": diff,
            "is_active": True,
        }

        result = get_db().table("prompt_versions").insert(row).execute()
        data = result.data
        row_data: dict[str, Any] = data[0] if isinstance(data, list) else data
        return row_data

    async def list_versions(
        self, agent_id: str, user_id: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        """List all versions for an agent, newest first."""
        result = (
            get_db().table("prompt_versions")
            .select("id,agent_id,version_number,change_summary,is_active,created_at")
            .eq("agent_id", agent_id)
            .eq("user_id", user_id)
            .order("version_number", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    async def get_version(
        self, version_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """Get a specific version with full prompt text."""
        result = (
            get_db().table("prompt_versions")
            .select("*")
            .eq("id", version_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        version_data: dict[str, Any] | None = result.data
        return version_data

    async def get_active_version(
        self, agent_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """Get the currently active version for an agent."""
        result = (
            get_db().table("prompt_versions")
            .select("*")
            .eq("agent_id", agent_id)
            .eq("user_id", user_id)
            .eq("is_active", True)
            .order("version_number", desc=True)
            .limit(1)
            .execute()
        )
        data = result.data
        return data[0] if data else None

    async def rollback(
        self, version_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """Rollback to a specific version — creates a new version with that prompt."""
        target = await self.get_version(version_id, user_id)
        if not target:
            return None

        agent_id = target["agent_id"]
        system_prompt = target["system_prompt"]
        target_version = target["version_number"]

        # Create new version with old content
        new_version = await self.create_version(
            user_id=user_id,
            agent_id=agent_id,
            system_prompt=system_prompt,
            change_summary=f"Rollback to v{target_version}",
        )

        # Also update the agent's system_prompt
        get_db().table("agents").update(
            {"system_prompt": system_prompt}
        ).eq("id", agent_id).eq("user_id", user_id).execute()

        return new_version

    async def diff_versions(
        self, version_a_id: str, version_b_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """Compare two versions and return their diff."""
        a = await self.get_version(version_a_id, user_id)
        b = await self.get_version(version_b_id, user_id)
        if not a or not b:
            return None

        diff = self._compute_diff(a["system_prompt"], b["system_prompt"])
        return {
            "version_a": {"id": a["id"], "version_number": a["version_number"]},
            "version_b": {"id": b["id"], "version_number": b["version_number"]},
            "diff": diff,
        }

    @staticmethod
    def _compute_diff(old_text: str, new_text: str) -> str:
        """Compute unified diff between two prompt texts."""
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        diff = difflib.unified_diff(old_lines, new_lines, fromfile="previous", tofile="current")
        return "".join(diff)


# Global singleton
prompt_version_service = PromptVersionService()
