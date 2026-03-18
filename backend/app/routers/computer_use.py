"""Computer use API endpoints — capability detection, status, and remote execution."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config.computer_use import cu_config
from app.routers.auth import get_current_user
from app.services.computer_use.detector import capability_detector
from app.services.computer_use.executor import test_remote_connection
from app.services.computer_use.safety import cu_rate_limiter

router = APIRouter(tags=["computer-use"])


@router.get("/computer-use/status")
async def computer_use_status(_user=Depends(get_current_user)):  # noqa: B008
    """Return the computer use capability report."""
    report = capability_detector.detect()
    return report.to_dict()


@router.post("/computer-use/refresh")
async def computer_use_refresh(_user=Depends(get_current_user)):  # noqa: B008
    """Force refresh the capability detection cache."""
    capability_detector.invalidate_cache()
    report = capability_detector.detect(force_refresh=True)
    return report.to_dict()


@router.get("/computer-use/config")
async def computer_use_config(_user=Depends(get_current_user)):  # noqa: B008
    """Return the current computer use configuration."""
    return {
        "execution_mode": cu_config.execution_mode,
        "listen_server_url": cu_config.listen_server_url or None,
        "listen_configured": bool(cu_config.listen_server_url),
        "require_approval": cu_config.require_approval,
        "max_actions_per_minute": cu_config.max_actions_per_minute,
        "app_blocklist": cu_config.app_blocklist,
        "command_blocklist": cu_config.command_blocklist,
        "dry_run": cu_config.dry_run,
        "rate_limit_remaining": cu_rate_limiter.remaining,
    }


@router.post("/computer-use/remote/test")
async def test_remote(_user=Depends(get_current_user)):  # noqa: B008
    """Test connection to the remote Listen server."""
    result = await test_remote_connection()
    return result


@router.get("/computer-use/audit-log")
async def audit_log(limit: int = 50, _user=Depends(get_current_user)):  # noqa: B008
    """Return recent computer use audit log entries."""
    from app.db import get_db

    try:
        result = (
            get_db().table("computer_use_audit_log")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception:
        return []
