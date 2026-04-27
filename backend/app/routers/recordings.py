"""Screen recording listing API."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from app.routers.auth import get_current_user

router = APIRouter(tags=["recordings"])


@router.get("/recordings")
async def list_recordings(_user=Depends(get_current_user)):  # noqa: B008
    """List recordings stored on disk.

    Mirrors the CLI's `forge recordings list` view. Recordings live on the
    filesystem at `AF_RECORDING_STORAGE` (defaults to /tmp/forge-recordings).
    Returns an empty list when the directory does not exist or is empty.
    """
    storage = os.getenv("AF_RECORDING_STORAGE", "/tmp/forge-recordings")
    if not os.path.isdir(storage):
        return []

    entries = []
    for name in sorted(os.listdir(storage), reverse=True)[:50]:
        path = os.path.join(storage, name)
        try:
            stat = os.stat(path)
        except OSError:
            continue
        entries.append(
            {
                "id": name,
                "blueprint": name.split("__", 1)[0] if "__" in name else "unknown",
                "target": "local",
                "duration_ms": 0,
                "started_at": _iso(stat.st_mtime),
                "trace_id": name.rsplit(".", 1)[0],
                "thumbnail_caption": name,
                "size_bytes": stat.st_size,
            }
        )
    return entries


def _iso(ts: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(ts, tz=UTC).isoformat()
