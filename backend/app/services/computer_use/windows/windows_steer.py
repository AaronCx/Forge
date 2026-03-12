"""Windows Steer implementation — GUI automation using pyautogui, pytesseract, pygetwindow."""

from __future__ import annotations

import asyncio
import base64
import io
import tempfile
from typing import Any


def _check_deps() -> None:
    """Verify Windows dependencies are available."""
    try:
        import pyautogui  # noqa: F401
    except ImportError:
        raise RuntimeError("pyautogui is required for Windows computer use: pip install pyautogui")


async def windows_steer_see(target: str = "screen", region: str = "") -> dict[str, Any]:
    """Capture a screenshot using pyautogui."""
    import pyautogui

    if target != "screen":
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(target)
            if windows:
                win = windows[0]
                win.activate()
                await asyncio.sleep(0.3)
                img = pyautogui.screenshot(region=(win.left, win.top, win.width, win.height))
            else:
                img = pyautogui.screenshot()
        except Exception:
            img = pyautogui.screenshot()
    else:
        img = pyautogui.screenshot()

    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
        img.save(path)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    return {"screenshot_path": path, "screenshot_base64": b64}


async def windows_steer_ocr(target: str = "screen", store: bool = False) -> dict[str, Any]:
    """OCR using pyautogui screenshot + pytesseract."""
    import pytesseract

    shot = await windows_steer_see(target=target)
    from PIL import Image
    img = Image.open(shot["screenshot_path"])

    if store:
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        elements = []
        for i, text in enumerate(data["text"]):
            if text.strip():
                elements.append({
                    "text": text,
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "width": data["width"][i],
                    "height": data["height"][i],
                })
        full_text = " ".join(e["text"] for e in elements)
        return {"text": full_text, "elements": elements, "element_count": len(elements)}
    else:
        text = pytesseract.image_to_string(img)
        return {"text": text, "elements": [], "element_count": 0}


async def windows_steer_click(x: int = 0, y: int = 0, element_text: str = "") -> dict[str, Any]:
    """Click at coordinates using pyautogui."""
    import pyautogui

    if element_text:
        ocr = await windows_steer_ocr(store=True)
        for el in ocr["elements"]:
            if element_text.lower() in el["text"].lower():
                x = el["x"] + el["width"] // 2
                y = el["y"] + el["height"] // 2
                break
        else:
            return {"success": False, "screenshot_after": ""}

    pyautogui.click(x, y)
    shot = await windows_steer_see()
    return {"success": True, "screenshot_after": shot["screenshot_base64"]}


async def windows_steer_type(text: str, target: str = "") -> dict[str, Any]:
    """Type text using pyautogui."""
    import pyautogui

    if target:
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(target)
            if windows:
                windows[0].activate()
                await asyncio.sleep(0.2)
        except Exception:
            pass

    pyautogui.write(text, interval=0.05)
    return {"success": True}


async def windows_steer_hotkey(keys: str) -> dict[str, Any]:
    """Send hotkey using pyautogui.hotkey."""
    import pyautogui

    # Convert "cmd+s" -> ("win", "s")
    parts = keys.replace("cmd", "win").replace("super", "win").split("+")
    pyautogui.hotkey(*[p.strip() for p in parts])
    return {"success": True}


async def windows_steer_scroll(direction: str = "down", amount: int = 3, target: str = "") -> dict[str, Any]:
    """Scroll using pyautogui."""
    import pyautogui

    if target:
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(target)
            if windows:
                windows[0].activate()
        except Exception:
            pass

    clicks = amount if direction == "up" else -amount
    pyautogui.scroll(clicks)
    return {"success": True}


async def windows_steer_drag(start_x: int, start_y: int, end_x: int, end_y: int) -> dict[str, Any]:
    """Drag using pyautogui."""
    import pyautogui

    pyautogui.moveTo(start_x, start_y)
    pyautogui.mouseDown()
    pyautogui.moveTo(end_x, end_y, duration=0.5)
    pyautogui.mouseUp()
    return {"success": True}


async def windows_steer_focus(app: str) -> dict[str, Any]:
    """Focus a window using pygetwindow."""
    try:
        import pygetwindow as gw
        windows = gw.getWindowsWithTitle(app)
        if windows:
            windows[0].activate()
            await asyncio.sleep(0.3)
            shot = await windows_steer_see()
            return {"success": True, "screenshot_base64": shot["screenshot_base64"]}
    except Exception:
        pass
    return {"success": False, "screenshot_base64": ""}


async def windows_steer_find(search_text: str) -> dict[str, Any]:
    """Find element via OCR."""
    ocr = await windows_steer_ocr(store=True)
    for el in ocr["elements"]:
        if search_text.lower() in el["text"].lower():
            return {
                "found": True,
                "coordinates": {"x": el["x"] + el["width"] // 2, "y": el["y"] + el["height"] // 2},
            }
    return {"found": False, "coordinates": {}}


async def windows_steer_wait(search_text: str, timeout: int = 10) -> dict[str, Any]:
    """Poll OCR until text appears or timeout."""
    elapsed = 0
    while elapsed < timeout:
        result = await windows_steer_find(search_text)
        if result["found"]:
            return {"condition_met": True}
        await asyncio.sleep(1)
        elapsed += 1
    return {"condition_met": False}


async def windows_steer_clipboard(action: str = "read", text: str = "") -> dict[str, Any]:
    """Clipboard access using pyperclip."""
    import pyperclip

    if action == "write":
        pyperclip.copy(text)
        return {"clipboard": text}
    else:
        return {"clipboard": pyperclip.paste()}


async def windows_steer_apps() -> dict[str, Any]:
    """List windows using pygetwindow."""
    import pygetwindow as gw

    all_windows = gw.getAllWindows()
    apps = [{"title": w.title, "visible": w.visible} for w in all_windows if w.title]
    return {"apps": apps, "app_count": len(apps)}


WINDOWS_STEER_MAP = {
    "steer_see": windows_steer_see,
    "steer_ocr": windows_steer_ocr,
    "steer_click": windows_steer_click,
    "steer_type": windows_steer_type,
    "steer_hotkey": windows_steer_hotkey,
    "steer_scroll": windows_steer_scroll,
    "steer_drag": windows_steer_drag,
    "steer_focus": windows_steer_focus,
    "steer_find": windows_steer_find,
    "steer_wait": windows_steer_wait,
    "steer_clipboard": windows_steer_clipboard,
    "steer_apps": windows_steer_apps,
}
