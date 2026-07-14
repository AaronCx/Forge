"""Golden-snapshot harness for the parity safety net.

The harness freezes the *current* observable behavior of every node executor
and of ``AgentRunner.execute`` so later harness-transformation phases can prove
they changed nothing they should not have. Snapshots live under ``golden/`` and
are compared byte-for-byte after normalization.

Regenerate goldens intentionally with ``FORGE_UPDATE_GOLDEN=1 pytest ...``.
A missing golden file is written and the test passes (first-run baseline);
committed goldens are then asserted against on every subsequent run.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path(__file__).parent / "golden"

# uuid-suffixed screenshot paths (absolute, user-specific) are the only volatile
# field emitted by the deterministic steer executors — collapse them so the
# snapshot is machine-independent.
_SCREENSHOT_RE = re.compile(r"[^\s\"']*steer_[0-9a-f]{12}\.png")
_SCREENSHOT_TOKEN = "<screenshot.png>"


def _update_mode() -> bool:
    return os.getenv("FORGE_UPDATE_GOLDEN", "") not in ("", "0", "false", "False")


def normalize(obj: Any) -> Any:
    """Recursively replace volatile substrings so snapshots are stable."""
    if isinstance(obj, str):
        return _SCREENSHOT_RE.sub(_SCREENSHOT_TOKEN, obj)
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize(v) for v in obj]
    return obj


def assert_golden(name: str, value: Any) -> None:
    """Compare ``value`` against ``golden/<name>.json`` (or create it).

    On a missing file (or in update mode) the golden is written and the test
    passes. Otherwise the normalized value must equal the stored golden exactly.
    """
    GOLDEN_DIR.mkdir(exist_ok=True)
    path = GOLDEN_DIR / f"{name}.json"
    normalized = normalize(value)
    serialized = json.dumps(normalized, indent=2, sort_keys=True, ensure_ascii=False)

    if _update_mode() or not path.exists():
        path.write_text(serialized + "\n", encoding="utf-8")
        return

    expected = path.read_text(encoding="utf-8").rstrip("\n")
    actual = serialized
    assert actual == expected, (
        f"parity snapshot drift for {name!r}. Re-run with FORGE_UPDATE_GOLDEN=1 "
        f"only if this change is intended.\n--- expected ---\n{expected}\n"
        f"--- actual ---\n{actual}"
    )
