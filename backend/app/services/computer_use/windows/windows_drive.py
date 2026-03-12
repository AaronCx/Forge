"""Windows Drive implementation — terminal control via PowerShell subprocess management."""

from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any


def _has_wsl() -> bool:
    """Check if WSL is available on Windows."""
    return shutil.which("wsl") is not None


def _has_tmux_via_wsl() -> bool:
    """Check if tmux is available inside WSL."""
    if not _has_wsl():
        return False
    try:
        import subprocess
        result = subprocess.run(
            ["wsl", "which", "tmux"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


async def _run_powershell(script: str, timeout: int = 30) -> str:
    """Execute a PowerShell command and return output."""
    proc = await asyncio.create_subprocess_exec(
        "powershell", "-NoProfile", "-Command", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0 and stderr:
        raise RuntimeError(f"PowerShell error: {stderr.decode().strip()}")
    return stdout.decode().strip() if stdout else ""


async def windows_drive_session(
    action: str = "create",
    session: str = "",
) -> dict[str, Any]:
    """Manage PowerShell sessions (or WSL tmux if available)."""
    if _has_tmux_via_wsl():
        # Use tmux through WSL
        if action == "create":
            await _run_wsl_tmux(f"new-session -d -s {session}")
            return {"session": session, "method": "wsl-tmux"}
        elif action == "list":
            output = await _run_wsl_tmux("list-sessions")
            sessions = [s.strip() for s in output.split("\n") if s.strip()]
            return {"sessions": sessions, "method": "wsl-tmux"}
        elif action == "kill":
            await _run_wsl_tmux(f"kill-session -t {session}")
            return {"session": session, "killed": True, "method": "wsl-tmux"}
    else:
        # PowerShell-based session management
        if action == "create":
            return {"session": session, "method": "powershell", "note": "PowerShell sessions are per-command"}
        elif action == "list":
            output = await _run_powershell("Get-Process powershell | Select-Object Id, StartTime | ConvertTo-Json")
            return {"sessions": [output], "method": "powershell"}
        elif action == "kill":
            return {"session": session, "killed": True, "method": "powershell"}

    return {"error": f"Unknown action: {action}"}


async def windows_drive_run(
    command: str,
    session: str = "",
    timeout: int = 30,
) -> dict[str, Any]:
    """Execute a command via PowerShell or WSL tmux."""
    if _has_tmux_via_wsl():
        # Route through WSL tmux
        await _run_wsl_tmux(f"send-keys -t {session} '{command}' Enter")
        await asyncio.sleep(1)
        output = await _run_wsl_tmux(f"capture-pane -t {session} -p")
        return {"text": output, "exit_code": 0, "method": "wsl-tmux"}
    else:
        output = await _run_powershell(command, timeout=timeout)
        return {"text": output, "exit_code": 0, "method": "powershell"}


async def windows_drive_logs(session: str = "", lines: int = 100) -> dict[str, Any]:
    """Capture output from WSL tmux pane or PowerShell transcript."""
    if _has_tmux_via_wsl():
        output = await _run_wsl_tmux(f"capture-pane -t {session} -p -S -{lines}")
        return {"text": output, "line_count": output.count("\n") + 1}
    return {"text": "", "line_count": 0, "note": "PowerShell transcript capture not available"}


async def _run_wsl_tmux(tmux_args: str, timeout: int = 30) -> str:
    """Run a tmux command through WSL."""
    proc = await asyncio.create_subprocess_exec(
        "wsl", "tmux", *tmux_args.split(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return stdout.decode().strip() if stdout else ""


def get_windows_drive_info() -> dict[str, Any]:
    """Get Windows terminal control capabilities."""
    return {
        "wsl_available": _has_wsl(),
        "tmux_via_wsl": _has_tmux_via_wsl(),
        "powershell": True,
        "method": "wsl-tmux" if _has_tmux_via_wsl() else "powershell",
    }


WINDOWS_DRIVE_MAP = {
    "drive_session": windows_drive_session,
    "drive_run": windows_drive_run,
    "drive_logs": windows_drive_logs,
}
