"""Computer use safety — blocklists, rate limiting, and audit logging."""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from typing import Any

from app.config.computer_use import cu_config
from app.db import get_db

logger = logging.getLogger(__name__)


class ActionRateLimiter:
    """Rate limiter for computer use actions."""

    def __init__(self, max_per_minute: int = 30) -> None:
        self.max_per_minute = max_per_minute
        self._timestamps: deque[float] = deque()

    def check(self) -> bool:
        """Return True if action is allowed, False if rate limited."""
        now = time.time()
        # Remove timestamps older than 60 seconds
        while self._timestamps and self._timestamps[0] < now - 60:
            self._timestamps.popleft()

        if len(self._timestamps) >= self.max_per_minute:
            return False

        self._timestamps.append(now)
        return True

    @property
    def remaining(self) -> int:
        now = time.time()
        while self._timestamps and self._timestamps[0] < now - 60:
            self._timestamps.popleft()
        return max(0, self.max_per_minute - len(self._timestamps))


cu_rate_limiter = ActionRateLimiter(max_per_minute=cu_config.max_actions_per_minute)


def check_app_blocklist(app_name: str) -> None:
    """Raise ValueError if the app is in the blocklist."""
    for blocked in cu_config.app_blocklist:
        if blocked.lower() in app_name.lower():
            raise ValueError(
                f"Computer use blocked: '{app_name}' is in the app blocklist. "
                f"Blocked apps: {', '.join(cu_config.app_blocklist)}"
            )


def check_command_blocklist(command: str) -> None:
    """Raise ValueError if the command matches a blocklist pattern.

    Uses whitespace-normalized matching to prevent bypass via extra spaces
    or special characters between tokens.
    """
    # Normalize: collapse whitespace, strip null bytes and control chars
    cmd_normalized = re.sub(r"[\x00-\x1f]+", " ", command)
    cmd_normalized = re.sub(r"\s+", " ", cmd_normalized).strip().lower()

    for blocked in cu_config.command_blocklist:
        blocked_normalized = re.sub(r"\s+", " ", blocked).strip().lower()
        if blocked_normalized in cmd_normalized:
            raise ValueError(
                f"Computer use blocked: command matches blocklist pattern '{blocked}'. "
                f"Blocked commands: {', '.join(cu_config.command_blocklist)}"
            )


def check_rate_limit() -> None:
    """Raise ValueError if rate limit exceeded."""
    if not cu_rate_limiter.check():
        raise ValueError(
            f"Computer use rate limit exceeded: max {cu_config.max_actions_per_minute} "
            f"actions per minute. Remaining: {cu_rate_limiter.remaining}"
        )


def log_action(
    *,
    node_type: str,
    command: str,
    arguments: dict[str, Any],
    target: str,
    result: str,
    screenshot_path: str | None = None,
    user_id: str = "",
    run_id: str = "",
    success: bool = True,
) -> None:
    """Log a computer use action to the audit log."""
    try:
        get_db().table("computer_use_audit_log").insert({
            "node_type": node_type,
            "command": command,
            "arguments": arguments,
            "target": target,
            "result": result[:2000],
            "screenshot_path": screenshot_path,
            "user_id": user_id,
            "run_id": run_id,
            "success": success,
        }).execute()
    except Exception:
        # Don't fail the action if audit logging fails — just log it
        logger.warning("Failed to write computer use audit log", exc_info=True)
