"""Trigger service — manages webhook, cron, and event triggers."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.db import get_db

logger = logging.getLogger(__name__)


class TriggerService:
    """Manages triggers and executes target agents/blueprints when fired."""

    async def create_trigger(
        self,
        *,
        user_id: str,
        trigger_type: str,
        config: dict[str, Any],
        target_type: str,
        target_id: str,
    ) -> dict[str, Any]:
        """Create a new trigger."""
        trigger_id = str(uuid.uuid4())
        webhook_secret = str(uuid.uuid4()) if trigger_type == "webhook" else None

        row = {
            "id": trigger_id,
            "user_id": user_id,
            "type": trigger_type,
            "config": {**config, **({"webhook_secret": webhook_secret} if webhook_secret else {})},
            "target_type": target_type,
            "target_id": target_id,
            "enabled": True,
            "fire_count": 0,
        }
        result = get_db().table("triggers").insert(row).execute()
        return result.data[0] if result.data else row

    async def list_triggers(self, user_id: str) -> list[dict[str, Any]]:
        """List all triggers for a user."""
        result = (
            get_db().table("triggers")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    async def get_trigger(self, trigger_id: str) -> dict[str, Any] | None:
        """Get a single trigger by ID."""
        result = (
            get_db().table("triggers")
            .select("*")
            .eq("id", trigger_id)
            .single()
            .execute()
        )
        data: dict[str, Any] | None = result.data
        return data

    async def update_trigger(
        self, trigger_id: str, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update a trigger's config."""
        result = (
            get_db().table("triggers")
            .update(updates)
            .eq("id", trigger_id)
            .execute()
        )
        return result.data[0] if result.data else None

    async def delete_trigger(self, trigger_id: str) -> bool:
        """Delete a trigger."""
        get_db().table("triggers").delete().eq("id", trigger_id).execute()
        return True

    async def toggle_trigger(self, trigger_id: str) -> dict[str, Any] | None:
        """Toggle a trigger's enabled state."""
        trigger = await self.get_trigger(trigger_id)
        if not trigger:
            return None
        new_state = not trigger.get("enabled", True)
        return await self.update_trigger(trigger_id, {"enabled": new_state})

    async def fire_trigger(
        self, trigger_id: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Fire a trigger — start the target agent or blueprint run."""
        trigger = await self.get_trigger(trigger_id)
        if not trigger:
            raise ValueError(f"Trigger {trigger_id} not found")
        if not trigger.get("enabled", True):
            raise ValueError(f"Trigger {trigger_id} is disabled")

        # Update fire count and last_fired_at
        get_db().table("triggers").update({
            "fire_count": (trigger.get("fire_count", 0) or 0) + 1,
            "last_fired_at": datetime.now(UTC).isoformat(),
        }).eq("id", trigger_id).execute()

        # Record firing in trigger_history
        history_row = {
            "id": str(uuid.uuid4()),
            "trigger_id": trigger_id,
            "payload": payload or {},
            "status": "fired",
        }
        get_db().table("trigger_history").insert(history_row).execute()

        target_type = trigger["target_type"]
        target_id = trigger["target_id"]
        user_id = trigger["user_id"]

        # Start the target run asynchronously
        if target_type == "agent":
            run_result = await self._start_agent_run(
                agent_id=target_id, user_id=user_id, payload=payload or {}
            )
        elif target_type == "blueprint":
            run_result = await self._start_blueprint_run(
                blueprint_id=target_id, user_id=user_id, payload=payload or {}
            )
        else:
            raise ValueError(f"Unknown target type: {target_type}")

        # Update history with run_id
        if run_result.get("run_id"):
            get_db().table("trigger_history").update({
                "run_id": run_result["run_id"],
                "status": "started",
            }).eq("id", history_row["id"]).execute()

        return {
            "trigger_id": trigger_id,
            "target_type": target_type,
            "target_id": target_id,
            "run_id": run_result.get("run_id"),
            "status": "fired",
        }

    async def _start_agent_run(
        self, *, agent_id: str, user_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Start an agent run from a trigger."""
        input_text = payload.get("input_text", payload.get("text", ""))
        if not input_text and payload:
            # Use the full payload as input if no explicit text
            import json
            input_text = json.dumps(payload)

        run_id = str(uuid.uuid4())
        get_db().table("runs").insert({
            "id": run_id,
            "agent_id": agent_id,
            "user_id": user_id,
            "input_text": input_text[:10000],
            "status": "pending",
            "tokens_used": 0,
            "step_logs": [],
        }).execute()

        return {"run_id": run_id}

    async def _start_blueprint_run(
        self, *, blueprint_id: str, user_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Start a blueprint run from a trigger."""
        run_id = str(uuid.uuid4())
        get_db().table("blueprint_runs").insert({
            "id": run_id,
            "blueprint_id": blueprint_id,
            "user_id": user_id,
            "status": "pending",
            "input_payload": payload,
            "execution_trace": [],
        }).execute()

        return {"run_id": run_id}

    async def get_trigger_history(
        self, trigger_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get recent firings for a trigger."""
        result = (
            get_db().table("trigger_history")
            .select("*")
            .eq("trigger_id", trigger_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def get_due_cron_triggers(self) -> list[dict[str, Any]]:
        """Get cron triggers that are due to fire (synchronous for scheduler use)."""
        result = (
            get_db().table("triggers")
            .select("*")
            .eq("type", "cron")
            .eq("enabled", True)
            .execute()
        )
        return result.data or []


trigger_service = TriggerService()
