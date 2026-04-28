"""Regression tests for QA Findings #6 and #7 — SQLite backend bugs surfaced
by the live-instance QA playbook run.

#6: WHERE clauses on joined queries used unqualified column names; tables that
    share a column (e.g. `created_at` on both `agent_heartbeats` and `agents`)
    raised `sqlite3.OperationalError: ambiguous column name`.

#7: `INSERT` returned the input dict unchanged, so DB-applied defaults
    (e.g. `is_template = 0` on `agents`) were missing from the response and
    pydantic 500'd during serialization while the row was already committed
    (phantom writes).
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def sqlite_backend(tmp_path):
    """Yield a fully-initialized SQLite backend on a throwaway DB."""
    from app.db.sqlite_backend import SQLiteBackend

    db = SQLiteBackend(db_path=str(tmp_path / "qa.db"))
    asyncio.run(db.initialize())
    return db


def test_insert_response_includes_db_defaults(sqlite_backend):
    """QA Finding #7: insert response must include DB-defaulted columns."""
    result = (
        sqlite_backend.table("agents")
        .insert(
            {
                "user_id": "22222222-2222-2222-2222-222222222222",
                "name": "regression-#7",
                "system_prompt": "x",
            }
        )
        .execute()
    )
    row = result.data[0]
    # is_template has DEFAULT 0 in the SQLite schema; must surface so pydantic
    # AgentResponse can validate without 500ing on a committed-but-leaked row.
    assert "is_template" in row, "insert response missing DB-defaulted column"
    assert row["is_template"] in (0, False)


def test_join_where_qualifies_ambiguous_column(sqlite_backend):
    """QA Finding #6: join + WHERE on a column shared by both tables works."""
    user_id = "11111111-1111-1111-1111-111111111111"
    agent = (
        sqlite_backend.table("agents")
        .insert({"user_id": user_id, "name": "regression-#6", "system_prompt": "x"})
        .execute()
    )
    agent_id = agent.data[0]["id"]
    sqlite_backend.table("agent_heartbeats").insert(
        {
            "agent_id": agent_id,
            "state": "running",
            "current_step": 0,
            "total_steps": 1,
            "tokens_used": 0,
            "cost_estimate": 0,
            "output_preview": "",
        }
    ).execute()

    # The query that broke /api/dashboard/metrics in the live-stack QA run.
    result = (
        sqlite_backend.table("agent_heartbeats")
        .select("tokens_used, agents!inner(user_id)")
        .eq("agents.user_id", user_id)
        .gte("created_at", "2000-01-01T00:00:00Z")
        .execute()
    )
    assert result.data, "join + created_at filter should return the heartbeat"


def test_order_by_qualifies_ambiguous_column(sqlite_backend):
    """QA Finding #28: ORDER BY on a column shared with a joined table must
    not raise 'ambiguous column name'. The breakdown query in
    token_tracker.get_breakdown joins agents in the SELECT and orders by
    `created_at` — both tables have one, so the bare reference broke
    /api/costs/all on SQLite the same way the WHERE clause did."""
    user_id = "33333333-3333-3333-3333-333333333333"
    sqlite_backend.table("agents").insert(
        {"user_id": user_id, "name": "regression-#28", "system_prompt": "x"}
    ).execute()

    # Mirrors token_tracker.get_breakdown: select with a join + ORDER BY created_at.
    result = (
        sqlite_backend.table("token_usage")
        .select("agent_id, model, provider, input_tokens, output_tokens, cost_usd, agents(name)")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    assert result.data == []  # no token_usage rows yet — important: should not raise
