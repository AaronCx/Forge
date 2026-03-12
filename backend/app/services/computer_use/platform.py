"""Cross-platform abstraction layer — unified interface for macOS, Linux, Windows."""

from __future__ import annotations

import platform as plat
import shutil
from typing import Any


def get_platform() -> str:
    """Detect the current platform."""
    system = plat.system()
    if system == "Darwin":
        return "macos"
    elif system == "Linux":
        return "linux"
    elif system == "Windows":
        return "windows"
    return "unknown"


def get_capabilities() -> dict[str, Any]:
    """Get available capabilities for the current platform."""
    p = get_platform()

    caps: dict[str, Any] = {
        "platform": p,
        "steer_available": False,
        "drive_available": False,
        "tmux_available": shutil.which("tmux") is not None,
    }

    if p == "macos":
        caps["steer_available"] = shutil.which("steer") is not None
        caps["drive_available"] = shutil.which("drive") is not None
        caps["steer_method"] = "steer-cli"
        caps["drive_method"] = "drive-cli"

    elif p == "linux":
        caps["steer_available"] = shutil.which("xdotool") is not None
        caps["drive_available"] = caps["tmux_available"]
        caps["steer_method"] = "xdotool"
        caps["drive_method"] = "tmux"
        # Extra Linux checks
        caps["xdotool"] = shutil.which("xdotool") is not None
        caps["tesseract"] = shutil.which("tesseract") is not None
        caps["scrot"] = shutil.which("scrot") is not None
        caps["wmctrl"] = shutil.which("wmctrl") is not None
        caps["xclip"] = shutil.which("xclip") is not None
        caps["xvfb"] = shutil.which("Xvfb") is not None

    elif p == "windows":
        try:
            import pyautogui  # noqa: F401
            caps["steer_available"] = True
        except ImportError:
            caps["steer_available"] = False
        caps["steer_method"] = "pyautogui"
        # Check WSL for tmux
        wsl = shutil.which("wsl") is not None
        caps["wsl_available"] = wsl
        caps["drive_available"] = True  # PowerShell always available
        caps["drive_method"] = "wsl-tmux" if wsl else "powershell"

    return caps


def get_steer_executor(node_type_key: str):
    """Get the platform-specific steer executor for a node type."""
    p = get_platform()

    if p == "macos":
        # macOS uses the Steer CLI via the standard executor
        return None  # Use default executor path

    elif p == "linux":
        from app.services.computer_use.linux.linux_steer import LINUX_STEER_MAP
        return LINUX_STEER_MAP.get(node_type_key)

    elif p == "windows":
        from app.services.computer_use.windows.windows_steer import WINDOWS_STEER_MAP
        return WINDOWS_STEER_MAP.get(node_type_key)

    return None


def get_drive_executor(node_type_key: str):
    """Get the platform-specific drive executor for a node type."""
    p = get_platform()

    if p == "macos" or p == "linux":
        # Both macOS and Linux use tmux-based Drive
        return None  # Use default executor path

    elif p == "windows":
        from app.services.computer_use.windows.windows_drive import WINDOWS_DRIVE_MAP
        return WINDOWS_DRIVE_MAP.get(node_type_key)

    return None


# Platform-specific install instructions
PLATFORM_INSTALL_INSTRUCTIONS = {
    "macos": {
        "steer": "Install Steer: see https://github.com/nickthecook/steer",
        "drive": "Install Drive: see https://github.com/nickthecook/drive",
        "tmux": "brew install tmux",
    },
    "linux": {
        "xdotool": "sudo apt install xdotool",
        "tesseract": "sudo apt install tesseract-ocr",
        "scrot": "sudo apt install scrot",
        "wmctrl": "sudo apt install wmctrl",
        "xclip": "sudo apt install xclip",
        "xvfb": "sudo apt install xvfb",
        "tmux": "sudo apt install tmux",
    },
    "windows": {
        "pyautogui": "pip install pyautogui",
        "pytesseract": "pip install pytesseract (also install tesseract binary)",
        "pygetwindow": "pip install pygetwindow",
        "pyperclip": "pip install pyperclip",
    },
}
