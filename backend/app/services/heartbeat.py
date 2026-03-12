"""Agent heartbeat service for real-time monitoring."""

from datetime import UTC, datetime, timedelta

from app.database import supabase

STALE_THRESHOLD_SECONDS = 30


class HeartbeatService:
    """Manages agent heartbeat state for live dashboard monitoring."""

    def start(self, agent_id: str, run_id: str, total_steps: int) -> str:
        """Create a heartbeat record when an agent run starts."""
        result = supabase.table("agent_heartbeats").insert({
            "agent_id": agent_id,
            "run_id": run_id,
            "state": "starting",
            "current_step": 0,
            "total_steps": total_steps,
            "tokens_used": 0,
            "cost_estimate": 0,
            "output_preview": "",
        }).execute()
        return result.data[0]["id"]

    def update(
        self,
        heartbeat_id: str,
        *,
        state: str | None = None,
        current_step: int | None = None,
        tokens_used: int | None = None,
        cost_estimate: float | None = None,
        output_preview: str | None = None,
    ):
        """Update a heartbeat with current progress."""
        data = {}
        if state is not None:
            data["state"] = state
        if current_step is not None:
            data["current_step"] = current_step
        if tokens_used is not None:
            data["tokens_used"] = tokens_used
        if cost_estimate is not None:
            data["cost_estimate"] = cost_estimate
        if output_preview is not None:
            data["output_preview"] = output_preview[:500]

        if data:
            supabase.table("agent_heartbeats").update(data).eq("id", heartbeat_id).execute()

    def complete(self, heartbeat_id: str, tokens_used: int = 0):
        """Mark a heartbeat as completed."""
        self.update(heartbeat_id, state="completed", tokens_used=tokens_used)

    def fail(self, heartbeat_id: str):
        """Mark a heartbeat as failed."""
        self.update(heartbeat_id, state="failed")

    def get_active(self) -> list[dict]:
        """Get all active (non-completed, non-failed) heartbeats."""
        result = (
            supabase.table("agent_heartbeats")
            .select("*, agents(name, description, tools)")
            .in_("state", ["starting", "running", "stalled"])
            .order("updated_at", desc=True)
            .execute()
        )
        return result.data or []

    def detect_stalled(self) -> list[dict]:
        """Find heartbeats that haven't been updated within the threshold."""
        threshold = (
            datetime.now(UTC) - timedelta(seconds=STALE_THRESHOLD_SECONDS)
        ).isoformat()

        result = (
            supabase.table("agent_heartbeats")
            .select("*")
            .in_("state", ["starting", "running"])
            .lt("updated_at", threshold)
            .execute()
        )

        stalled = result.data or []
        for hb in stalled:
            self.update(hb["id"], state="stalled")

        return stalled

    def get_metrics(self) -> dict:
        """Get aggregate dashboard metrics."""
        active = (
            supabase.table("agent_heartbeats")
            .select("id", count="exact")
            .in_("state", ["starting", "running"])
            .execute()
        )

        all_today = (
            supabase.table("agent_heartbeats")
            .select("tokens_used, cost_estimate", count="exact")
            .gte("created_at", datetime.now(UTC).replace(hour=0, minute=0, second=0).isoformat())
            .execute()
        )

        tokens_today = sum(r.get("tokens_used", 0) for r in (all_today.data or []))
        cost_today = sum(float(r.get("cost_estimate", 0)) for r in (all_today.data or []))

        total_agents = supabase.table("agents").select("id", count="exact").execute()

        return {
            "active_runs": active.count or 0,
            "total_agents": total_agents.count or 0,
            "tokens_today": tokens_today,
            "cost_today": round(cost_today, 4),
        }


heartbeat_service = HeartbeatService()
