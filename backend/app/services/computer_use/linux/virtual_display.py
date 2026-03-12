"""Xvfb virtual display management for headless Linux computer use."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class VirtualDisplay:
    """Manages Xvfb virtual framebuffers for headless Linux GUI automation."""

    def __init__(self) -> None:
        self._processes: dict[int, asyncio.subprocess.Process] = {}

    async def start(
        self,
        display_number: int = 99,
        width: int = 1920,
        height: int = 1080,
        depth: int = 24,
    ) -> dict[str, Any]:
        """Start Xvfb with a virtual screen."""
        screen_spec = f"{width}x{height}x{depth}"
        display = f":{display_number}"

        proc = await asyncio.create_subprocess_exec(
            "Xvfb", display, "-screen", "0", screen_spec, "-ac",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._processes[display_number] = proc

        # Set DISPLAY for subsequent commands
        os.environ["DISPLAY"] = display

        logger.info("Started Xvfb on %s (%s)", display, screen_spec)
        return {
            "display": display,
            "resolution": f"{width}x{height}",
            "depth": depth,
            "pid": proc.pid,
        }

    async def stop(self, display_number: int = 99) -> dict[str, Any]:
        """Stop the virtual framebuffer."""
        proc = self._processes.pop(display_number, None)
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
            return {"stopped": True, "display": f":{display_number}"}
        return {"stopped": False, "display": f":{display_number}"}

    def set_display(self, display_number: int = 99) -> str:
        """Set the DISPLAY environment variable."""
        display = f":{display_number}"
        os.environ["DISPLAY"] = display
        return display

    def is_running(self, display_number: int = 99) -> bool:
        """Check if a virtual display is running."""
        proc = self._processes.get(display_number)
        return proc is not None and proc.returncode is None


virtual_display = VirtualDisplay()
