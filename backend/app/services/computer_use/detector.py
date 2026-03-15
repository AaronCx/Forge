"""Computer use capability detection — checks for Steer, Drive, and tmux availability."""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CapabilityReport:
    """Report of available computer use capabilities."""

    steer_available: bool = False
    steer_version: str = ""
    steer_commands: list[str] = field(default_factory=list)
    drive_available: bool = False
    drive_version: str = ""
    drive_commands: list[str] = field(default_factory=list)
    tmux_available: bool = False
    tmux_version: str = ""
    macos_version: str = ""
    is_macos: bool = False
    missing: list[str] = field(default_factory=list)
    install_instructions: dict[str, str] = field(default_factory=dict)

    platform_name: str = "unknown"  # "macos", "linux", "windows"
    # Linux-specific capabilities
    xdotool_available: bool = False
    tesseract_available: bool = False
    scrot_available: bool = False
    wmctrl_available: bool = False
    xclip_available: bool = False
    xvfb_available: bool = False
    # Windows-specific capabilities
    pyautogui_available: bool = False
    wsl_available: bool = False
    # Agent backends
    agent_backends: list[str] = field(default_factory=list)

    # macOS permissions
    accessibility_permission: bool = False
    screen_recording_permission: bool = False
    # Detected system commands
    detected_commands: dict[str, bool] = field(default_factory=dict)
    ffmpeg_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "steer_available": self.steer_available,
            "steer_version": self.steer_version,
            "steer_commands": self.steer_commands,
            "drive_available": self.drive_available,
            "drive_version": self.drive_version,
            "drive_commands": self.drive_commands,
            "tmux_available": self.tmux_available,
            "tmux_version": self.tmux_version,
            "ffmpeg_available": self.ffmpeg_available,
            "macos_version": self.macos_version,
            "is_macos": self.is_macos,
            "platform": self.platform_name,
            "computer_use_ready": self.steer_available and self.drive_available,
            "missing": self.missing,
            "install_instructions": self.install_instructions,
            # Permissions (macOS)
            "accessibility_permission": self.accessibility_permission,
            "screen_recording_permission": self.screen_recording_permission,
            # Detected system commands
            "detected_commands": self.detected_commands,
            # Linux
            "xdotool_available": self.xdotool_available,
            "tesseract_available": self.tesseract_available,
            "scrot_available": self.scrot_available,
            "wmctrl_available": self.wmctrl_available,
            "xclip_available": self.xclip_available,
            "xvfb_available": self.xvfb_available,
            # Windows
            "pyautogui_available": self.pyautogui_available,
            "wsl_available": self.wsl_available,
            # Agent backends
            "agent_backends": self.agent_backends,
        }


def _run_version(binary: str) -> str | None:
    """Run '<binary> --version' and return version string, or None."""
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0]
        return result.stderr.strip().split("\n")[0] if result.stderr else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _get_commands(binary: str) -> list[str]:
    """Get available commands from a CLI tool's help output."""
    try:
        result = subprocess.run(
            [binary, "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = result.stdout + result.stderr
        # Parse commands from help text (common patterns)
        commands = []
        in_commands = False
        for line in output.split("\n"):
            stripped = line.strip()
            if stripped.lower().startswith("commands:") or stripped.lower().startswith("available commands:"):
                in_commands = True
                continue
            if in_commands:
                if not stripped or stripped.startswith("-"):
                    break
                cmd = stripped.split()[0] if stripped.split() else ""
                if cmd and not cmd.startswith("-"):
                    commands.append(cmd)
        return commands
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


class CapabilityDetector:
    """Detects and caches computer use capabilities."""

    def __init__(self) -> None:
        self._cached_report: CapabilityReport | None = None

    def detect(self, force_refresh: bool = False) -> CapabilityReport:
        """Detect available computer use capabilities. Results are cached."""
        if self._cached_report and not force_refresh:
            return self._cached_report

        report = CapabilityReport()

        # Detect platform
        system = platform.system()
        report.is_macos = system == "Darwin"
        if report.is_macos:
            report.platform_name = "macos"
            report.macos_version = platform.mac_ver()[0]
        elif system == "Linux":
            report.platform_name = "linux"
        elif system == "Windows":
            report.platform_name = "windows"

        # --- macOS: Check Steer & Drive CLIs ---
        if report.is_macos:
            steer_path = shutil.which("steer")
            if steer_path:
                version = _run_version("steer")
                report.steer_available = True
                report.steer_version = version or "unknown"
                report.steer_commands = _get_commands("steer")
            else:
                report.missing.append("steer")
                report.install_instructions["steer"] = (
                    "Install Steer CLI for GUI automation:\n"
                    "  brew install disler/tap/steer\n"
                    "  # Or: pip install steer-cli"
                )

            drive_path = shutil.which("drive")
            if drive_path:
                version = _run_version("drive")
                report.drive_available = True
                report.drive_version = version or "unknown"
                report.drive_commands = _get_commands("drive")
            else:
                report.missing.append("drive")
                report.install_instructions["drive"] = (
                    "Install Drive CLI for terminal automation:\n"
                    "  brew install disler/tap/drive\n"
                    "  # Or: pip install drive-cli"
                )

        # --- Linux: Check xdotool, tesseract, scrot, wmctrl, xclip, Xvfb ---
        elif report.platform_name == "linux":
            linux_tools = {
                "xdotool": "xdotool_available",
                "tesseract": "tesseract_available",
                "scrot": "scrot_available",
                "wmctrl": "wmctrl_available",
                "xclip": "xclip_available",
                "Xvfb": "xvfb_available",
            }
            for tool, attr in linux_tools.items():
                if shutil.which(tool):
                    setattr(report, attr, True)
                else:
                    report.missing.append(tool)
                    report.install_instructions[tool] = f"sudo apt install {tool.lower()}"

            # Steer available if xdotool is present
            report.steer_available = report.xdotool_available
            if report.steer_available:
                report.steer_version = "linux-xdotool"
            # Drive available if tmux is present
            report.drive_available = shutil.which("tmux") is not None

        # --- Windows: Check pyautogui, WSL ---
        elif report.platform_name == "windows":
            try:
                import pyautogui  # noqa: F401
                report.pyautogui_available = True
                report.steer_available = True
                report.steer_version = "windows-pyautogui"
            except ImportError:
                report.missing.append("pyautogui")
                report.install_instructions["pyautogui"] = "pip install pyautogui"

            report.wsl_available = shutil.which("wsl") is not None
            report.drive_available = True  # PowerShell always available
            report.drive_version = "powershell" + (" + wsl-tmux" if report.wsl_available else "")

        # --- macOS permissions ---
        if report.is_macos:
            report.detected_commands = {
                "screencapture": shutil.which("screencapture") is not None,
                "cliclick": shutil.which("cliclick") is not None,
                "osascript": shutil.which("osascript") is not None,
                "tmux": shutil.which("tmux") is not None,
                "ffmpeg": shutil.which("ffmpeg") is not None,
            }
            report.ffmpeg_available = report.detected_commands.get("ffmpeg", False)

            # Check screen recording by attempting a screenshot
            try:
                import tempfile
                import os
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    tmp = f.name
                result = subprocess.run(
                    ["screencapture", "-x", tmp],
                    capture_output=True, timeout=5,
                )
                if result.returncode == 0 and os.path.exists(tmp):
                    size = os.path.getsize(tmp)
                    report.screen_recording_permission = size > 1000
                    os.unlink(tmp)
                else:
                    report.screen_recording_permission = False
            except Exception:
                report.screen_recording_permission = False

            # Check accessibility (simplified — avoid hanging osascript)
            try:
                result = subprocess.run(
                    ["osascript", "-e", 'tell application "System Events" to count of (every process)'],
                    capture_output=True, text=True, timeout=3,
                )
                report.accessibility_permission = result.returncode == 0
            except (subprocess.TimeoutExpired, Exception):
                report.accessibility_permission = False

        # --- Common: Check tmux ---
        tmux_path = shutil.which("tmux")
        if tmux_path:
            version = _run_version("tmux")
            report.tmux_available = True
            report.tmux_version = version or "unknown"
        else:
            if "tmux" not in report.missing:
                report.missing.append("tmux")
            report.install_instructions.setdefault("tmux", "brew install tmux")

        # --- Check agent backends ---
        from app.config.agent_backends import BUILTIN_BACKENDS
        for name, backend in BUILTIN_BACKENDS.items():
            if shutil.which(backend.command):
                report.agent_backends.append(name)

        self._cached_report = report
        return report

    def invalidate_cache(self) -> None:
        """Clear the cached capability report."""
        self._cached_report = None


capability_detector = CapabilityDetector()
