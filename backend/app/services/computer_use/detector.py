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
            "macos_version": self.macos_version,
            "is_macos": self.is_macos,
            "computer_use_ready": self.steer_available and self.drive_available and self.tmux_available,
            "missing": self.missing,
            "install_instructions": self.install_instructions,
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

        # Check macOS
        report.is_macos = platform.system() == "Darwin"
        if report.is_macos:
            report.macos_version = platform.mac_ver()[0]

        # Check Steer
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

        # Check Drive
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

        # Check tmux
        tmux_path = shutil.which("tmux")
        if tmux_path:
            version = _run_version("tmux")
            report.tmux_available = True
            report.tmux_version = version or "unknown"
        else:
            report.missing.append("tmux")
            report.install_instructions["tmux"] = (
                "Install tmux (required by Drive):\n"
                "  brew install tmux"
            )

        if not report.is_macos:
            report.missing.append("macos")
            report.install_instructions["macos"] = (
                "Computer use requires macOS. Run AgentForge's backend on a Mac,\n"
                "or configure remote execution to dispatch to a Mac Mini via Listen."
            )

        self._cached_report = report
        return report

    def invalidate_cache(self) -> None:
        """Clear the cached capability report."""
        self._cached_report = None


capability_detector = CapabilityDetector()
