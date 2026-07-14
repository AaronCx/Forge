"""Per-user cost budgets (harness-plan.md Phase 7).

A user's daily USD budget comes from ``user_preferences.daily_budget_usd``
(0 = unlimited) or the ``FORGE_DAILY_USD_BUDGET`` env default. Spend is today's
``token_usage`` cost. ``check_user_budget`` is called before a session turn so a
run refuses instead of overspending.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from app.db import get_db
from app.services.token_tracker import token_tracker

logger = logging.getLogger(__name__)


@dataclass
class BudgetStatus:
    within_budget: bool
    spent_usd: float
    limit_usd: float  # 0 = unlimited

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.limit_usd - self.spent_usd) if self.limit_usd else float("inf")


def _env_default_limit() -> float:
    try:
        return float(os.getenv("FORGE_DAILY_USD_BUDGET", "0") or 0)
    except ValueError:
        return 0.0


def user_daily_limit(user_id: str | None) -> float:
    """The user's daily USD limit (0 = unlimited)."""
    default = _env_default_limit()
    if not user_id:
        return default
    try:
        result = (
            get_db().table("user_preferences").select("daily_budget_usd")
            .eq("user_id", user_id).execute()
        )
        rows = result.data if isinstance(result.data, list) else []
        if rows and rows[0].get("daily_budget_usd"):
            return float(rows[0]["daily_budget_usd"])
    except Exception as exc:  # noqa: BLE001 - budgets are best-effort
        logger.debug("daily budget read failed for %s: %s", user_id, exc)
    return default


def today_spend(user_id: str | None) -> float:
    if not user_id:
        return 0.0
    try:
        return float(token_tracker.get_summary(user_id, "today").get("total_cost", 0.0))
    except Exception as exc:  # noqa: BLE001
        logger.debug("today spend read failed for %s: %s", user_id, exc)
        return 0.0


def check_user_budget(user_id: str | None) -> BudgetStatus:
    """Whether the user is within their daily budget (unlimited if limit is 0)."""
    limit = user_daily_limit(user_id)
    spent = today_spend(user_id)
    within = limit == 0 or spent < limit
    return BudgetStatus(within_budget=within, spent_usd=round(spent, 6), limit_usd=limit)
