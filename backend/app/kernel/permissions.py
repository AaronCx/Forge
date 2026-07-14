"""Permission policy for the tool plane (harness-plan.md Phase 3).

One decision function governs every tool call. Resolution order:

1. per-session override (ephemeral, set on the ExecContext)
2. per-user policy (the ``tool_policies`` table)
3. default by the tool's ``danger_level`` (safe=allow, caution/dangerous=ask)

An ``ask`` decision routes through the existing approvals inbox (web + CLI) —
one inbox for everything, no new UI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from app.kernel.types import DangerLevel, ToolSpec

logger = logging.getLogger(__name__)

PolicyDecision = Literal["allow", "ask", "deny"]

_DEFAULT_BY_DANGER: dict[DangerLevel, PolicyDecision] = {
    "safe": "allow",
    "caution": "ask",
    "dangerous": "ask",
}


def default_decision(spec: ToolSpec) -> PolicyDecision:
    """The decision implied by a tool's danger level, absent any policy."""
    if spec.requires_approval:
        return "ask"
    return _DEFAULT_BY_DANGER.get(spec.danger_level, "ask")


@dataclass
class PermissionResolver:
    """Resolves a tool call to allow/ask/deny.

    ``session_overrides`` and ``user_policies`` are name→decision maps; the
    former (per-session) wins over the latter (per-user), which wins over the
    danger-level default.
    """

    user_policies: dict[str, PolicyDecision] = field(default_factory=dict)
    session_overrides: dict[str, PolicyDecision] = field(default_factory=dict)

    def decide(self, spec: ToolSpec) -> PolicyDecision:
        if spec.name in self.session_overrides:
            return self.session_overrides[spec.name]
        if spec.name in self.user_policies:
            return self.user_policies[spec.name]
        return default_decision(spec)


async def load_user_tool_policies(user_id: str | None) -> dict[str, PolicyDecision]:
    """Load a user's stored allow/ask/deny decisions from ``tool_policies``."""
    if not user_id:
        return {}
    from app.db import get_db

    try:
        result = (
            get_db()
            .table("tool_policies")
            .select("tool_name, decision")
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 - policies are best-effort
        logger.debug("tool_policies read failed for %s: %s", user_id, exc)
        return {}

    policies: dict[str, PolicyDecision] = {}
    rows = result.data if isinstance(result.data, list) else []
    for row in rows:
        decision = row.get("decision")
        name = row.get("tool_name")
        if name and decision in ("allow", "ask", "deny"):
            policies[name] = decision
    return policies
