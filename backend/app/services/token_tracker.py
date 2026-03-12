"""Token tracking service with cost calculation."""

from datetime import UTC, datetime, timedelta

from app.database import supabase

# Pricing per 1M tokens (USD)
MODEL_PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}

DEFAULT_MODEL = "gpt-4o-mini"


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for a given model and token counts."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING[DEFAULT_MODEL])
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)


class TokenTracker:
    """Tracks token usage per run step and provides cost analytics."""

    def record(
        self,
        *,
        run_id: str,
        agent_id: str,
        user_id: str,
        step_number: int,
        model: str = DEFAULT_MODEL,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> dict:
        """Record token usage for a single step."""
        cost = calculate_cost(model, input_tokens, output_tokens)

        result = supabase.table("token_usage").insert({
            "run_id": run_id,
            "agent_id": agent_id,
            "user_id": user_id,
            "step_number": step_number,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
        }).execute()

        return result.data[0] if result.data else {}

    def get_summary(self, user_id: str, period: str = "today") -> dict:
        """Get cost summary for a period (today, week, month)."""
        now = datetime.now(UTC)
        if period == "today":
            since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            since = now - timedelta(days=7)
        elif period == "month":
            since = now - timedelta(days=30)
        else:
            since = now.replace(hour=0, minute=0, second=0, microsecond=0)

        result = (
            supabase.table("token_usage")
            .select("input_tokens, output_tokens, cost_usd, model")
            .eq("user_id", user_id)
            .gte("created_at", since.isoformat())
            .execute()
        )

        rows = result.data or []
        total_input = sum(r.get("input_tokens", 0) for r in rows)
        total_output = sum(r.get("output_tokens", 0) for r in rows)
        total_cost = sum(float(r.get("cost_usd", 0)) for r in rows)

        return {
            "period": period,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "total_cost": round(total_cost, 6),
            "request_count": len(rows),
        }

    def get_breakdown(self, user_id: str, group_by: str = "agent") -> list[dict]:
        """Get cost breakdown grouped by agent or model."""
        result = (
            supabase.table("token_usage")
            .select("agent_id, model, input_tokens, output_tokens, cost_usd, agents(name)")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )

        rows = result.data or []
        groups: dict[str, dict] = {}

        for row in rows:
            if group_by == "agent":
                key = row.get("agents", {}).get("name", "Unknown") if row.get("agents") else row.get("agent_id", "Unknown")
            else:
                key = row.get("model", DEFAULT_MODEL)

            if key not in groups:
                groups[key] = {"name": key, "input_tokens": 0, "output_tokens": 0, "cost": 0, "requests": 0}

            groups[key]["input_tokens"] += row.get("input_tokens", 0)
            groups[key]["output_tokens"] += row.get("output_tokens", 0)
            groups[key]["cost"] += float(row.get("cost_usd", 0))
            groups[key]["requests"] += 1

        result_list = list(groups.values())
        for g in result_list:
            g["cost"] = round(g["cost"], 6)
        return sorted(result_list, key=lambda x: x["cost"], reverse=True)

    def get_run_usage(self, run_id: str) -> list[dict]:
        """Get step-by-step token usage for a specific run."""
        result = (
            supabase.table("token_usage")
            .select("*")
            .eq("run_id", run_id)
            .order("step_number")
            .execute()
        )
        return result.data or []

    def get_projection(self, user_id: str) -> dict:
        """Project monthly cost based on recent usage."""
        week_summary = self.get_summary(user_id, "week")
        daily_avg = week_summary["total_cost"] / 7 if week_summary["total_cost"] > 0 else 0
        monthly_projection = round(daily_avg * 30, 2)

        return {
            "daily_average": round(daily_avg, 4),
            "weekly_total": week_summary["total_cost"],
            "monthly_projection": monthly_projection,
            "tokens_per_day": int(week_summary["total_tokens"] / 7) if week_summary["total_tokens"] > 0 else 0,
        }


token_tracker = TokenTracker()
