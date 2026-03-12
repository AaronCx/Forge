"""Linux Steer implementation — GUI automation using xdotool, scrot, tesseract, wmctrl, xclip."""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any


async def _run(cmd: list[str], timeout: int = 30) -> str:
    """Run a CLI command and return stdout."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        err = stderr.decode().strip() if stderr else ""
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(cmd)}: {err}")
    return stdout.decode().strip() if stdout else ""


async def linux_steer_see(target: str = "screen", region: str = "") -> dict[str, Any]:
    """Capture a screenshot using scrot or maim."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name

    if target == "screen":
        await _run(["scrot", path])
    else:
        # Try to capture specific window by focusing it first
        try:
            await _run(["wmctrl", "-a", target])
            await asyncio.sleep(0.3)
        except RuntimeError:
            pass
        await _run(["scrot", "-u", path])

    import base64
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    return {"screenshot_path": path, "screenshot_base64": b64}


async def linux_steer_ocr(target: str = "screen", store: bool = False) -> dict[str, Any]:
    """OCR using scrot + tesseract."""
    shot = await linux_steer_see(target=target)
    path = shot["screenshot_path"]

    if store:
        # Get bounding boxes via TSV output
        output = await _run(["tesseract", path, "stdout", "--psm", "11", "tsv"])
        elements = []
        for line in output.split("\n")[1:]:
            parts = line.split("\t")
            if len(parts) >= 12 and parts[11].strip():
                elements.append({
                    "text": parts[11],
                    "x": int(parts[6]),
                    "y": int(parts[7]),
                    "width": int(parts[8]),
                    "height": int(parts[9]),
                })
        text = " ".join(e["text"] for e in elements)
        return {"text": text, "elements": elements, "element_count": len(elements)}
    else:
        text = await _run(["tesseract", path, "stdout"])
        return {"text": text, "elements": [], "element_count": 0}


async def linux_steer_click(x: int = 0, y: int = 0, element_text: str = "") -> dict[str, Any]:
    """Click at coordinates or on a text element using xdotool."""
    if element_text:
        # OCR to find element position, then click center
        ocr = await linux_steer_ocr(store=True)
        for el in ocr["elements"]:
            if element_text.lower() in el["text"].lower():
                x = el["x"] + el["width"] // 2
                y = el["y"] + el["height"] // 2
                break
        else:
            return {"success": False, "screenshot_after": "", "error": f"Element '{element_text}' not found"}

    await _run(["xdotool", "mousemove", str(x), str(y)])
    await _run(["xdotool", "click", "1"])

    shot = await linux_steer_see()
    return {"success": True, "screenshot_after": shot["screenshot_base64"]}


async def linux_steer_type(text: str, target: str = "") -> dict[str, Any]:
    """Type text using xdotool."""
    if target:
        try:
            await _run(["wmctrl", "-a", target])
            await asyncio.sleep(0.2)
        except RuntimeError:
            pass
    await _run(["xdotool", "type", "--delay", "50", text])
    return {"success": True}


async def linux_steer_hotkey(keys: str) -> dict[str, Any]:
    """Send hotkey using xdotool key."""
    # Convert "cmd+s" format to xdotool format "super+s"
    xdo_keys = keys.replace("cmd", "super").replace("+", "+")
    await _run(["xdotool", "key", xdo_keys])
    return {"success": True}


async def linux_steer_scroll(direction: str = "down", amount: int = 3, target: str = "") -> dict[str, Any]:
    """Scroll using xdotool click (button 4=up, 5=down)."""
    if target:
        try:
            await _run(["wmctrl", "-a", target])
        except RuntimeError:
            pass

    button = "4" if direction == "up" else "5"
    for _ in range(amount):
        await _run(["xdotool", "click", button])
    return {"success": True}


async def linux_steer_drag(start_x: int, start_y: int, end_x: int, end_y: int) -> dict[str, Any]:
    """Drag from one point to another using xdotool."""
    await _run(["xdotool", "mousemove", str(start_x), str(start_y)])
    await _run(["xdotool", "mousedown", "1"])
    await _run(["xdotool", "mousemove", str(end_x), str(end_y)])
    await _run(["xdotool", "mouseup", "1"])
    return {"success": True}


async def linux_steer_focus(app: str) -> dict[str, Any]:
    """Focus a window using wmctrl or xdotool."""
    try:
        await _run(["wmctrl", "-a", app])
    except RuntimeError:
        # Fallback to xdotool search
        wid = await _run(["xdotool", "search", "--name", app])
        if wid:
            first_wid = wid.split("\n")[0].strip()
            await _run(["xdotool", "windowactivate", first_wid])

    await asyncio.sleep(0.3)
    shot = await linux_steer_see()
    return {"success": True, "screenshot_base64": shot["screenshot_base64"]}


async def linux_steer_find(search_text: str) -> dict[str, Any]:
    """Find a UI element by running OCR and searching."""
    ocr = await linux_steer_ocr(store=True)
    for el in ocr["elements"]:
        if search_text.lower() in el["text"].lower():
            return {
                "found": True,
                "coordinates": {"x": el["x"] + el["width"] // 2, "y": el["y"] + el["height"] // 2},
            }
    return {"found": False, "coordinates": {}}


async def linux_steer_wait(search_text: str, timeout: int = 10) -> dict[str, Any]:
    """Poll OCR until text appears or timeout."""
    elapsed = 0
    while elapsed < timeout:
        result = await linux_steer_find(search_text)
        if result["found"]:
            return {"condition_met": True}
        await asyncio.sleep(1)
        elapsed += 1
    return {"condition_met": False}


async def linux_steer_clipboard(action: str = "read", text: str = "") -> dict[str, Any]:
    """Read/write clipboard using xclip."""
    if action == "write":
        proc = await asyncio.create_subprocess_exec(
            "xclip", "-selection", "clipboard",
            stdin=asyncio.subprocess.PIPE,
        )
        await proc.communicate(input=text.encode())
        return {"clipboard": text}
    else:
        output = await _run(["xclip", "-selection", "clipboard", "-o"])
        return {"clipboard": output}


async def linux_steer_apps() -> dict[str, Any]:
    """List windows using wmctrl."""
    output = await _run(["wmctrl", "-l"])
    apps = []
    for line in output.split("\n"):
        parts = line.split(None, 3)
        if len(parts) >= 4:
            apps.append({"title": parts[3], "window_id": parts[0]})
    return {"apps": apps, "app_count": len(apps)}


# Map of command -> implementation
LINUX_STEER_MAP = {
    "steer_see": linux_steer_see,
    "steer_ocr": linux_steer_ocr,
    "steer_click": linux_steer_click,
    "steer_type": linux_steer_type,
    "steer_hotkey": linux_steer_hotkey,
    "steer_scroll": linux_steer_scroll,
    "steer_drag": linux_steer_drag,
    "steer_focus": linux_steer_focus,
    "steer_find": linux_steer_find,
    "steer_wait": linux_steer_wait,
    "steer_clipboard": linux_steer_clipboard,
    "steer_apps": linux_steer_apps,
}
