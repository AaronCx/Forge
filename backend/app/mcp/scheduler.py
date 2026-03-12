"""Cron scheduler — checks for due cron triggers and fires them."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from croniter import croniter  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class CronScheduler:
    """Simple cron scheduler that checks for due triggers every minute."""

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Start the scheduler background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Cron scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Cron scheduler stopped")

    async def _run_loop(self) -> None:
        """Main loop — check for due triggers every 60 seconds."""
        from app.mcp.triggers import trigger_service

        while self._running:
            try:
                await self._check_triggers(trigger_service)
            except Exception:
                logger.warning("Cron check failed", exc_info=True)
            await asyncio.sleep(60)

    async def _check_triggers(self, trigger_service: object) -> None:
        """Check all cron triggers and fire any that are due."""
        from app.mcp.triggers import TriggerService

        assert isinstance(trigger_service, TriggerService)
        triggers = trigger_service.get_due_cron_triggers()
        now = datetime.now(UTC)

        for trigger in triggers:
            config = trigger.get("config", {})
            cron_expr = config.get("cron_expression", "")
            if not cron_expr:
                continue

            try:
                last_fired = trigger.get("last_fired_at")
                if last_fired:
                    if isinstance(last_fired, str):
                        last_fired_dt = datetime.fromisoformat(last_fired.replace("Z", "+00:00"))
                    else:
                        last_fired_dt = last_fired
                else:
                    # Never fired — use created_at as base
                    created = trigger.get("created_at", now.isoformat())
                    if isinstance(created, str):
                        last_fired_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    else:
                        last_fired_dt = created

                cron = croniter(cron_expr, last_fired_dt)
                next_fire = cron.get_next(datetime)

                # Make next_fire timezone-aware if needed
                if next_fire.tzinfo is None:
                    next_fire = next_fire.replace(tzinfo=UTC)

                if next_fire <= now:
                    logger.info(
                        "Firing cron trigger %s (expression: %s)",
                        trigger["id"],
                        cron_expr,
                    )
                    await trigger_service.fire_trigger(
                        trigger["id"],
                        payload={"triggered_by": "cron", "cron_expression": cron_expr},
                    )
            except Exception:
                logger.warning(
                    "Failed to process cron trigger %s", trigger["id"], exc_info=True
                )

    @staticmethod
    def validate_cron(expression: str) -> bool:
        """Validate a cron expression."""
        try:
            croniter(expression)
            return True
        except (ValueError, KeyError):
            return False

    @staticmethod
    def next_fire_time(expression: str) -> datetime | None:
        """Get the next fire time for a cron expression."""
        try:
            cron = croniter(expression, datetime.now(UTC))
            result: datetime = cron.get_next(datetime)
            return result
        except (ValueError, KeyError):
            return None


cron_scheduler = CronScheduler()
