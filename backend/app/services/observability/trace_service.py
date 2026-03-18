"""Trace service — records execution spans for observability."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.db import get_db

logger = logging.getLogger(__name__)


class TraceService:
    """Records and queries execution traces (spans)."""

    async def start_span(
        self,
        *,
        user_id: str,
        span_type: str,
        span_name: str,
        run_id: str | None = None,
        blueprint_run_id: str | None = None,
        agent_id: str | None = None,
        parent_span_id: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        input_preview: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new span and return it."""
        row: dict[str, Any] = {
            "user_id": user_id,
            "span_type": span_type,
            "span_name": span_name,
            "status": "running",
            "input_preview": input_preview[:2000],
            "metadata": metadata or {},
            "started_at": datetime.now(UTC).isoformat(),
        }
        if run_id:
            row["run_id"] = run_id
        if blueprint_run_id:
            row["blueprint_run_id"] = blueprint_run_id
        if agent_id:
            row["agent_id"] = agent_id
        if parent_span_id:
            row["parent_span_id"] = parent_span_id
        if model:
            row["model"] = model
        if provider:
            row["provider"] = provider

        result = get_db().table("traces").insert(row).execute()
        data = result.data
        span_data: dict[str, Any] = data[0] if isinstance(data, list) else data
        return span_data

    async def end_span(
        self,
        span_id: str,
        *,
        status: str = "ok",
        output_preview: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: float = 0,
        error_message: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> dict[str, Any] | None:
        """Complete a span with results."""
        update: dict[str, Any] = {
            "status": status,
            "output_preview": output_preview[:2000],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "ended_at": datetime.now(UTC).isoformat(),
        }
        if error_message:
            update["error_message"] = error_message
        if model:
            update["model"] = model
        if provider:
            update["provider"] = provider

        result = get_db().table("traces").update(update).eq("id", span_id).execute()
        data = result.data
        if not data:
            return None
        ended_data: dict[str, Any] = data[0] if isinstance(data, list) else data
        return ended_data

    async def record_span(
        self,
        *,
        user_id: str,
        span_type: str,
        span_name: str,
        run_id: str | None = None,
        blueprint_run_id: str | None = None,
        agent_id: str | None = None,
        parent_span_id: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: float = 0,
        status: str = "ok",
        input_preview: str = "",
        output_preview: str = "",
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a completed span in one call."""
        now = datetime.now(UTC).isoformat()
        row: dict[str, Any] = {
            "user_id": user_id,
            "span_type": span_type,
            "span_name": span_name,
            "model": model,
            "provider": provider,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "status": status,
            "input_preview": input_preview[:2000],
            "output_preview": output_preview[:2000],
            "error_message": error_message,
            "metadata": metadata or {},
            "started_at": now,
            "ended_at": now,
        }
        if run_id:
            row["run_id"] = run_id
        if blueprint_run_id:
            row["blueprint_run_id"] = blueprint_run_id
        if agent_id:
            row["agent_id"] = agent_id
        if parent_span_id:
            row["parent_span_id"] = parent_span_id

        result = get_db().table("traces").insert(row).execute()
        data = result.data
        row_data: dict[str, Any] = data[0] if isinstance(data, list) else data
        return row_data

    async def list_traces(
        self,
        user_id: str,
        *,
        run_id: str | None = None,
        blueprint_run_id: str | None = None,
        agent_id: str | None = None,
        span_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List traces for a user with optional filters."""
        query = get_db().table("traces").select("*").eq("user_id", user_id)

        if run_id:
            query = query.eq("run_id", run_id)
        if blueprint_run_id:
            query = query.eq("blueprint_run_id", blueprint_run_id)
        if agent_id:
            query = query.eq("agent_id", agent_id)
        if span_type:
            query = query.eq("span_type", span_type)

        result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        return result.data or []

    async def get_trace(self, trace_id: str, user_id: str) -> dict[str, Any] | None:
        """Get a single trace by ID."""
        result = (
            get_db().table("traces")
            .select("*")
            .eq("id", trace_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        trace_data: dict[str, Any] | None = result.data
        return trace_data

    async def get_trace_tree(self, trace_id: str, user_id: str) -> dict[str, Any]:
        """Get a trace and all its child spans (one level deep)."""
        parent = await self.get_trace(trace_id, user_id)
        if not parent:
            return {}

        children = (
            get_db().table("traces")
            .select("*")
            .eq("parent_span_id", trace_id)
            .eq("user_id", user_id)
            .order("started_at")
            .execute()
        ).data or []

        parent["children"] = children
        return parent

    async def get_trace_stats(self, user_id: str, *, days: int = 7) -> dict[str, Any]:
        """Get aggregated trace statistics."""
        # Get recent traces for stats
        traces = (
            get_db().table("traces")
            .select("span_type,status,input_tokens,output_tokens,latency_ms")
            .eq("user_id", user_id)
            .gte("created_at", datetime.now(UTC).replace(hour=0, minute=0, second=0).isoformat())
            .execute()
        ).data or []

        total = len(traces)
        errors = sum(1 for t in traces if t.get("status") == "error")
        total_tokens = sum((t.get("input_tokens", 0) or 0) + (t.get("output_tokens", 0) or 0) for t in traces)
        total_latency = sum(t.get("latency_ms", 0) or 0 for t in traces)
        avg_latency = total_latency / total if total > 0 else 0

        by_type: dict[str, int] = {}
        for t in traces:
            st = t.get("span_type", "unknown")
            by_type[st] = by_type.get(st, 0) + 1

        return {
            "total_spans": total,
            "error_count": errors,
            "error_rate": errors / total if total > 0 else 0,
            "total_tokens": total_tokens,
            "avg_latency_ms": round(avg_latency, 1),
            "by_type": by_type,
        }


# Global singleton
trace_service = TraceService()
