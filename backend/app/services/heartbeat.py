"""Agent heartbeat service for real-time monitoring."""

from datetime import UTC, datetime, timedelta

from app.db import get_db

STALE_THRESHOLD_SECONDS = 30


class HeartbeatService:
    """Manages agent heartbeat state for live dashboard monitoring."""

    def start(self, agent_id: str, run_id: str, total_steps: int) -> str:
        """Create a heartbeat record when an agent run starts."""
        result = get_db().table("agent_heartbeats").insert({
            "agent_id": agent_id,
            "run_id": run_id,
            "state": "starting",
            "current_step": 0,
            "total_steps": total_steps,
            "tokens_used": 0,
            "cost_estimate": 0,
            "output_preview": "",
        }).execute()
        return str(result.data[0]["id"])

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
        data: dict[str, str | int | float] = {}
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
            get_db().table("agent_heartbeats").update(data).eq("id", heartbeat_id).execute()

    def complete(self, heartbeat_id: str, tokens_used: int = 0):
        """Mark a heartbeat as completed."""
        self.update(heartbeat_id, state="completed", tokens_used=tokens_used)

    def fail(self, heartbeat_id: str):
        """Mark a heartbeat as failed."""
        self.update(heartbeat_id, state="failed")

    def get_active(self, user_id: str | None = None) -> list[dict]:
        """Get all active (non-completed, non-failed) heartbeats."""
        query = (
            get_db().table("agent_heartbeats")
            .select("*, agents(name, description, tools, user_id)")
            .in_("state", ["starting", "running", "stalled"])
            .order("updated_at", desc=True)
        )
        if user_id:
            query = query.eq("agents.user_id", user_id)
        result = query.execute()
        # Filter out rows where the agents join returned null (user_id mismatch)
        if user_id:
            return [r for r in (result.data or []) if r.get("agents")]
        return result.data or []

    def detect_stalled(self, user_id: str | None = None) -> list[dict]:
        """Find heartbeats that haven't been updated within the threshold."""
        threshold = (
            datetime.now(UTC) - timedelta(seconds=STALE_THRESHOLD_SECONDS)
        ).isoformat()

        query = (
            get_db().table("agent_heartbeats")
            .select("*, agents!inner(user_id)")
            .in_("state", ["starting", "running"])
            .lt("updated_at", threshold)
        )
        if user_id:
            query = query.eq("agents.user_id", user_id)
        result = query.execute()

        stalled = result.data or []
        for hb in stalled:
            self.update(hb["id"], state="stalled")

        return stalled

    def get_metrics(self, user_id: str | None = None) -> dict:
        """Get aggregate dashboard metrics."""
        active_query = (
            get_db().table("agent_heartbeats")
            .select("id, agents!inner(user_id)", count="exact")  # type: ignore[arg-type]
            .in_("state", ["starting", "running"])
        )
        if user_id:
            active_query = active_query.eq("agents.user_id", user_id)
        active = active_query.execute()

        today_query = (
            get_db().table("agent_heartbeats")
            .select("tokens_used, cost_estimate, agents!inner(user_id)", count="exact")  # type: ignore[arg-type]
            .gte("created_at", datetime.now(UTC).replace(hour=0, minute=0, second=0).isoformat())
        )
        if user_id:
            today_query = today_query.eq("agents.user_id", user_id)
        all_today = today_query.execute()

        tokens_today = sum(r.get("tokens_used", 0) for r in (all_today.data or []))
        cost_today = sum(float(r.get("cost_estimate", 0)) for r in (all_today.data or []))

        agents_query = get_db().table("agents").select("id", count="exact")  # type: ignore[arg-type]
        if user_id:
            agents_query = agents_query.eq("user_id", user_id)
        total_agents = agents_query.execute()

        return {
            "active_runs": active.count or 0,
            "total_agents": total_agents.count or 0,
            "tokens_today": tokens_today,
            "cost_today": round(cost_today, 4),
        }


heartbeat_service = HeartbeatService()
