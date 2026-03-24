"""Screen recording service — capture video of agent sessions."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from app.config.computer_use import cu_config
from app.services.computer_use.safety import check_rate_limit, log_action

logger = logging.getLogger(__name__)

# Recording config defaults
RECORDING_QUALITY = {
    "low": {"resolution": "1280x720", "fps": "15"},
    "medium": {"resolution": "1920x1080", "fps": "30"},
    "high": {"resolution": "native", "fps": "30"},
}


class RecorderService:
    """Manages screen recording sessions for computer use blueprints."""

    def __init__(self) -> None:
        self._active_recordings: dict[str, dict[str, Any]] = {}
        self._storage_path = os.getenv("AF_RECORDING_STORAGE", "/tmp/forge-recordings")

    async def start_recording(
        self,
        run_id: str,
        target_id: str = "local",
        quality: str = "medium",
    ) -> dict[str, Any]:
        """Begin capturing the screen on the target machine."""
        os.makedirs(self._storage_path, exist_ok=True)
        filename = f"recording-{run_id}-{int(time.time())}.mp4"
        filepath = os.path.join(self._storage_path, filename)

        quality_settings = RECORDING_QUALITY.get(quality, RECORDING_QUALITY["medium"])

        if cu_config.dry_run:
            self._active_recordings[run_id] = {
                "filepath": filepath,
                "target_id": target_id,
                "quality": quality,
                "start_time": time.time(),
                "process": None,
            }
            return {"recording_path": filepath, "status": "recording", "dry_run": True}

        # Use ffmpeg with avfoundation (macOS) or x11grab (Linux)
        import platform as plat
        if plat.system() == "Darwin":
            cmd = [
                "ffmpeg", "-y", "-f", "avfoundation", "-framerate", quality_settings["fps"],
                "-i", "1:none", "-c:v", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", filepath,
            ]
        else:
            display = os.getenv("DISPLAY", ":0")
            res = quality_settings["resolution"] if quality_settings["resolution"] != "native" else "1920x1080"
            cmd = [
                "ffmpeg", "-y", "-f", "x11grab", "-framerate", quality_settings["fps"],
                "-video_size", res, "-i", display,
                "-c:v", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", filepath,
            ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            self._active_recordings[run_id] = {
                "filepath": filepath,
                "target_id": target_id,
                "quality": quality,
                "start_time": time.time(),
                "process": proc,
            }
            log_action(
                node_type="recording_control",
                command="start_recording",
                arguments={"run_id": run_id, "quality": quality},
                target=target_id,
                result=f"Recording to {filename}",
            )
            return {"recording_path": filepath, "status": "recording"}
        except FileNotFoundError:
            logger.warning("ffmpeg not found — screen recording unavailable")
            return {"recording_path": "", "status": "unavailable", "error": "ffmpeg not installed"}

    async def stop_recording(self, run_id: str) -> dict[str, Any]:
        """Stop capture and return the video file path."""
        recording = self._active_recordings.pop(run_id, None)
        if not recording:
            return {"recording_path": "", "status": "not_found"}

        proc = recording.get("process")
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except TimeoutError:
                proc.kill()

        duration = time.time() - recording["start_time"]
        filepath = recording["filepath"]
        size_bytes = os.path.getsize(filepath) if os.path.exists(filepath) else 0

        log_action(
            node_type="recording_control",
            command="stop_recording",
            arguments={"run_id": run_id},
            target=recording.get("target_id", "local"),
            result=f"Recorded {duration:.1f}s, {size_bytes} bytes",
        )

        return {
            "recording_path": filepath,
            "status": "available",
            "duration_seconds": round(duration, 1),
            "size_bytes": size_bytes,
        }

    async def get_recording(self, run_id: str) -> dict[str, Any]:
        """Get recording info for a completed run."""
        # Check active recordings
        if run_id in self._active_recordings:
            return {"status": "recording", "recording_path": self._active_recordings[run_id]["filepath"]}
        # Check storage
        for f in os.listdir(self._storage_path) if os.path.exists(self._storage_path) else []:
            if run_id in f:
                path = os.path.join(self._storage_path, f)
                return {
                    "status": "available",
                    "recording_path": path,
                    "size_bytes": os.path.getsize(path),
                }
        return {"status": "not_found"}

    def cleanup_recordings(self, older_than_days: int = 30) -> int:
        """Delete recordings older than N days."""
        if not os.path.exists(self._storage_path):
            return 0
        cutoff = time.time() - (older_than_days * 86400)
        removed = 0
        for f in os.listdir(self._storage_path):
            path = os.path.join(self._storage_path, f)
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        return removed


recorder_service = RecorderService()


# --- recording_control node executor ---

async def execute_recording_control(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Start or stop screen recording during a blueprint run."""
    check_rate_limit()
    action = config.get("action", "start")
    quality = config.get("quality", "medium")
    run_id = inputs.get("_run_id", "unknown")

    if action == "start":
        result = await recorder_service.start_recording(run_id=run_id, quality=quality)
    elif action == "stop":
        result = await recorder_service.stop_recording(run_id=run_id)
    else:
        raise ValueError(f"recording_control: unknown action '{action}' (use start/stop)")

    return {
        "text": f"Recording {action}: {result.get('status', 'unknown')}",
        "recording_path": result.get("recording_path", ""),
        "status": result.get("status", "unknown"),
        "success": result.get("status") != "unavailable",
    }


RECORDING_EXECUTORS = {
    "recording_control": execute_recording_control,
}
