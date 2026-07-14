"""Feature flags for the harness transformation (harness-plan.md guardrail 4).

Each flag gates a new subsystem that is built alongside the old one and cut over
only once its phase's exit criteria pass. All default OFF. Flags are read live
from the environment on each call so tests and the CLI can toggle them without
reimporting, and so a deploy can flip one without a code change.

Truthy values: ``1``, ``true``, ``yes``, ``on`` (case-insensitive).
"""

from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}

# Flag name -> default when the env var is unset.
# Phase 8 (cutover) flipped these on: the native loop is now the only stack, and
# sessions/MCP-v2 are the supported surfaces. Set the env var to a falsy value to
# opt out on a given install.
_DEFAULTS: dict[str, bool] = {
    "FORGE_NATIVE_LOOP": True,
    "FORGE_MCP_V2": True,
    "FORGE_SESSIONS": True,
}


def _enabled(name: str) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return _DEFAULTS.get(name, False)
    return raw.strip().lower() in _TRUTHY


def native_loop_enabled() -> bool:
    """FORGE_NATIVE_LOOP — use the kernel agent loop instead of LangChain."""
    return _enabled("FORGE_NATIVE_LOOP")


def mcp_v2_enabled() -> bool:
    """FORGE_MCP_V2 — use the real MCP (JSON-RPC) client for new connections."""
    return _enabled("FORGE_MCP_V2")


def sessions_enabled() -> bool:
    """FORGE_SESSIONS — expose durable sessions and the chat surface."""
    return _enabled("FORGE_SESSIONS")


def all_flags() -> dict[str, bool]:
    """Snapshot of every flag's current value (for diagnostics endpoints)."""
    return {name: _enabled(name) for name in _DEFAULTS}
