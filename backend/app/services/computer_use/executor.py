"""Computer use executor — routes commands through local CLI or remote Listen server."""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from typing import Any

import httpx

from app.config.computer_use import cu_config

logger = logging.getLogger(__name__)


async def run_local(binary: str, args: list[str], timeout: int = 30) -> dict[str, Any]:
    """Execute a Steer or Drive CLI command locally."""
    cmd = [binary] + args
    logger.info("Computer use local exec: %s", " ".join(cmd))

    if cu_config.dry_run:
        return {
            "success": True,
            "output": f"[DRY RUN] Would execute: {' '.join(cmd)}",
            "exit_code": 0,
            "dry_run": True,
        }

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        output = stdout.decode("utf-8", errors="replace")
        errors = stderr.decode("utf-8", errors="replace")

        # Try to parse JSON output
        try:
            parsed = json.loads(output)
            return {
                "success": proc.returncode == 0,
                "output": parsed,
                "exit_code": proc.returncode,
                "stderr": errors if errors else None,
            }
        except json.JSONDecodeError:
            return {
                "success": proc.returncode == 0,
                "output": output.strip(),
                "exit_code": proc.returncode,
                "stderr": errors if errors else None,
            }

    except asyncio.TimeoutError:
        return {
            "success": False,
            "output": f"Command timed out after {timeout}s",
            "exit_code": -1,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "output": f"Binary not found: {binary}",
            "exit_code": -1,
        }


async def run_remote(command_payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a computer use command to a remote Listen job server."""
    if not cu_config.listen_server_url:
        raise ValueError(
            "Remote execution configured but CU_LISTEN_URL is not set. "
            "Set CU_LISTEN_URL to the Listen server address."
        )

    headers = {"Content-Type": "application/json"}
    if cu_config.listen_api_key:
        headers["Authorization"] = f"Bearer {cu_config.listen_api_key}"

    async with httpx.AsyncClient(timeout=60) as client:
        # Submit job
        resp = await client.post(
            f"{cu_config.listen_server_url}/job",
            json={"prompt": json.dumps(command_payload)},
            headers=headers,
        )
        resp.raise_for_status()
        job = resp.json()
        job_id = job.get("id", job.get("job_id", ""))

        if not job_id:
            return {"success": True, "output": job}

        # Poll for completion
        for _ in range(120):  # 2 minutes max
            await asyncio.sleep(1)
            status_resp = await client.get(
                f"{cu_config.listen_server_url}/job/{job_id}",
                headers=headers,
            )
            if status_resp.status_code == 200:
                status = status_resp.json()
                if status.get("status") in ("completed", "failed", "done"):
                    return {
                        "success": status.get("status") != "failed",
                        "output": status.get("result", status.get("output", "")),
                        "job_id": job_id,
                    }

        return {
            "success": False,
            "output": "Remote job timed out after 120s",
            "job_id": job_id,
        }


async def execute(binary: str, args: list[str], timeout: int = 30) -> dict[str, Any]:
    """Execute a computer use command via local CLI or remote Listen server."""
    if cu_config.execution_mode == "remote":
        return await run_remote({
            "binary": binary,
            "args": args,
            "timeout": timeout,
        })
    return await run_local(binary, args, timeout=timeout)


async def test_remote_connection() -> dict[str, Any]:
    """Test connection to the remote Listen server."""
    if not cu_config.listen_server_url:
        return {"connected": False, "error": "CU_LISTEN_URL not configured"}

    headers = {}
    if cu_config.listen_api_key:
        headers["Authorization"] = f"Bearer {cu_config.listen_api_key}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{cu_config.listen_server_url}/jobs",
                headers=headers,
            )
            return {
                "connected": resp.status_code == 200,
                "status_code": resp.status_code,
                "server_url": cu_config.listen_server_url,
            }
    except Exception as e:
        return {"connected": False, "error": str(e)}
