"""Steer node executors — GUI automation via Steer CLI."""

from __future__ import annotations

import base64
import os
import uuid
from typing import Any

from app.config.computer_use import cu_config
from app.services.computer_use.executor import execute
from app.services.computer_use.safety import (
    check_app_blocklist,
    check_rate_limit,
    log_action,
)


def _screenshot_path() -> str:
    """Generate a unique screenshot file path."""
    os.makedirs(cu_config.screenshot_dir, exist_ok=True)
    return os.path.join(cu_config.screenshot_dir, f"steer_{uuid.uuid4().hex[:12]}.png")


async def execute_steer_see(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Capture a screenshot of a specific app, window, or the full screen."""
    check_rate_limit()
    target = config.get("target") or inputs.get("target", "screen")
    region = config.get("region")

    if target != "screen":
        check_app_blocklist(target)

    args = ["see"]
    if target and target != "screen":
        args.extend(["--app", target])
    if region:
        args.extend(["--region", region])

    output_path = _screenshot_path()
    args.extend(["--output", output_path])

    result = await execute("steer", args)

    screenshot_data = ""
    if os.path.exists(output_path):
        with open(output_path, "rb") as f:
            screenshot_data = base64.b64encode(f.read()).decode("utf-8")

    log_action(
        node_type="steer_see",
        command="see",
        arguments={"target": target, "region": region},
        target=target,
        result="screenshot captured" if result["success"] else str(result["output"]),
        screenshot_path=output_path if os.path.exists(output_path) else None,
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    return {
        "text": f"Screenshot captured: {target}",
        "screenshot_path": output_path,
        "screenshot_base64": screenshot_data,
        "target": target,
        "success": result["success"],
    }


async def execute_steer_ocr(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Extract text from the screen or app window using OCR."""
    check_rate_limit()
    target = config.get("target") or inputs.get("target", "screen")
    store = config.get("store", False)

    if target != "screen":
        check_app_blocklist(target)

    args = ["ocr"]
    if target and target != "screen":
        args.extend(["--app", target])
    if store:
        args.append("--store")

    result = await execute("steer", args)

    elements = []
    if isinstance(result["output"], list):
        elements = result["output"]
    elif isinstance(result["output"], str):
        elements = [{"text": line, "index": i} for i, line in enumerate(result["output"].split("\n")) if line.strip()]

    log_action(
        node_type="steer_ocr",
        command="ocr",
        arguments={"target": target, "store": store},
        target=target,
        result=f"Found {len(elements)} elements",
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    text_content = "\n".join(e.get("text", str(e)) if isinstance(e, dict) else str(e) for e in elements)

    return {
        "text": text_content,
        "elements": elements,
        "element_count": len(elements),
        "target": target,
        "success": result["success"],
    }


async def execute_steer_click(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Click at coordinates or on a detected text element."""
    check_rate_limit()
    x = config.get("x")
    y = config.get("y")
    element_text = config.get("element_text") or inputs.get("element_text")
    target = config.get("target") or inputs.get("target", "")

    if target:
        check_app_blocklist(target)

    args = ["click"]
    if x is not None and y is not None:
        args.extend([str(int(x)), str(int(y))])
    elif element_text:
        args.extend(["--text", element_text])
    else:
        raise ValueError("steer_click requires either (x, y) coordinates or element_text")

    result = await execute("steer", args)

    # Capture screenshot after click for verification
    after_path = _screenshot_path()
    await execute("steer", ["see", "--output", after_path])

    after_b64 = ""
    if os.path.exists(after_path):
        with open(after_path, "rb") as f:
            after_b64 = base64.b64encode(f.read()).decode("utf-8")

    log_action(
        node_type="steer_click",
        command="click",
        arguments={"x": x, "y": y, "element_text": element_text},
        target=target or f"({x}, {y})",
        result="clicked" if result["success"] else str(result["output"]),
        screenshot_path=after_path if os.path.exists(after_path) else None,
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    return {
        "text": f"Clicked at {'(' + str(x) + ', ' + str(y) + ')' if x is not None else element_text}",
        "screenshot_after": after_b64,
        "screenshot_path": after_path,
        "success": result["success"],
    }


async def execute_steer_type(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Type text into the currently focused application."""
    check_rate_limit()
    text = config.get("text") or inputs.get("text", "")
    target = config.get("target") or inputs.get("target", "")

    if target:
        check_app_blocklist(target)

    if not text:
        raise ValueError("steer_type: 'text' is required")

    args = ["type", text]
    if target:
        args.extend(["--app", target])

    result = await execute("steer", args)

    log_action(
        node_type="steer_type",
        command="type",
        arguments={"text": text[:100], "target": target},
        target=target or "focused app",
        result="typed" if result["success"] else str(result["output"]),
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    return {
        "text": f"Typed {len(text)} characters",
        "success": result["success"],
    }


async def execute_steer_hotkey(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Send a keyboard shortcut."""
    check_rate_limit()
    keys = config.get("keys") or config.get("hotkey") or inputs.get("keys", "")

    if not keys:
        raise ValueError("steer_hotkey: 'keys' is required (e.g. 'cmd+s')")

    args = ["hotkey", keys]
    result = await execute("steer", args)

    log_action(
        node_type="steer_hotkey",
        command="hotkey",
        arguments={"keys": keys},
        target="keyboard",
        result="sent" if result["success"] else str(result["output"]),
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    return {
        "text": f"Sent hotkey: {keys}",
        "success": result["success"],
    }


async def execute_steer_scroll(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Scroll in a direction within an app."""
    check_rate_limit()
    direction = config.get("direction", "down")
    amount = config.get("amount", 3)
    target = config.get("target") or inputs.get("target", "")

    if target:
        check_app_blocklist(target)

    args = ["scroll", direction, str(int(amount))]
    if target:
        args.extend(["--app", target])

    result = await execute("steer", args)

    log_action(
        node_type="steer_scroll",
        command="scroll",
        arguments={"direction": direction, "amount": amount, "target": target},
        target=target or "focused app",
        result="scrolled" if result["success"] else str(result["output"]),
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    return {
        "text": f"Scrolled {direction} by {amount}",
        "success": result["success"],
    }


async def execute_steer_drag(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Drag from one point to another."""
    check_rate_limit()
    start_x = config.get("start_x", 0)
    start_y = config.get("start_y", 0)
    end_x = config.get("end_x", 0)
    end_y = config.get("end_y", 0)

    args = ["drag", str(int(start_x)), str(int(start_y)), str(int(end_x)), str(int(end_y))]
    result = await execute("steer", args)

    log_action(
        node_type="steer_drag",
        command="drag",
        arguments={"start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y},
        target=f"({start_x},{start_y}) -> ({end_x},{end_y})",
        result="dragged" if result["success"] else str(result["output"]),
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    return {
        "text": f"Dragged from ({start_x},{start_y}) to ({end_x},{end_y})",
        "success": result["success"],
    }


async def execute_steer_focus(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Activate and bring a specific app to the foreground."""
    check_rate_limit()
    app_name = config.get("app") or config.get("target") or inputs.get("app", "")

    if not app_name:
        raise ValueError("steer_focus: 'app' is required")

    check_app_blocklist(app_name)

    args = ["focus", app_name]
    result = await execute("steer", args)

    # Take screenshot of focused app
    screenshot_path = _screenshot_path()
    await execute("steer", ["see", "--app", app_name, "--output", screenshot_path])

    screenshot_b64 = ""
    if os.path.exists(screenshot_path):
        with open(screenshot_path, "rb") as f:
            screenshot_b64 = base64.b64encode(f.read()).decode("utf-8")

    log_action(
        node_type="steer_focus",
        command="focus",
        arguments={"app": app_name},
        target=app_name,
        result="focused" if result["success"] else str(result["output"]),
        screenshot_path=screenshot_path if os.path.exists(screenshot_path) else None,
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    return {
        "text": f"Focused app: {app_name}",
        "screenshot_base64": screenshot_b64,
        "screenshot_path": screenshot_path,
        "success": result["success"],
    }


async def execute_steer_find(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Locate a UI element on screen by text or description."""
    check_rate_limit()
    search_text = config.get("search_text") or inputs.get("search_text", "")

    if not search_text:
        raise ValueError("steer_find: 'search_text' is required")

    args = ["find", search_text]
    result = await execute("steer", args)

    found = result["success"] and result.get("output")
    coordinates = None
    if isinstance(result["output"], dict):
        coordinates = result["output"]
    elif isinstance(result["output"], str) and result["success"]:
        # Try to parse coordinate output
        try:
            parts = result["output"].strip().split(",")
            if len(parts) >= 2:
                coordinates = {"x": int(parts[0]), "y": int(parts[1])}
        except (ValueError, IndexError):
            pass

    log_action(
        node_type="steer_find",
        command="find",
        arguments={"search_text": search_text},
        target="screen",
        result=f"found at {coordinates}" if found else "not found",
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=found,
    )

    return {
        "text": f"Element '{search_text}' {'found' if found else 'not found'}",
        "found": found,
        "coordinates": coordinates,
        "success": result["success"],
    }


async def execute_steer_wait(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Wait for a condition to be met on screen."""
    check_rate_limit()
    search_text = config.get("search_text") or inputs.get("search_text", "")
    timeout = int(config.get("timeout", 10))

    if not search_text:
        raise ValueError("steer_wait: 'search_text' is required")

    args = ["wait", search_text, "--timeout", str(timeout)]
    result = await execute("steer", args, timeout=timeout + 5)

    log_action(
        node_type="steer_wait",
        command="wait",
        arguments={"search_text": search_text, "timeout": timeout},
        target="screen",
        result="condition met" if result["success"] else "timed out",
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    return {
        "text": f"Wait for '{search_text}': {'met' if result['success'] else 'timed out'}",
        "condition_met": result["success"],
        "success": result["success"],
    }


async def execute_steer_clipboard(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Read from or write to the system clipboard."""
    check_rate_limit()
    action = config.get("action", "read")
    text = config.get("text") or inputs.get("text", "")

    args = ["clipboard", action]
    if action == "write" and text:
        args.append(text)

    result = await execute("steer", args)

    clipboard_content = ""
    if action == "read" and result["success"]:
        clipboard_content = str(result["output"])

    log_action(
        node_type="steer_clipboard",
        command="clipboard",
        arguments={"action": action},
        target="clipboard",
        result=f"{'read' if action == 'read' else 'written'}" if result["success"] else str(result["output"]),
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    return {
        "text": clipboard_content if action == "read" else f"Wrote {len(text)} chars to clipboard",
        "clipboard": clipboard_content,
        "success": result["success"],
    }


async def execute_steer_apps(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """List all running applications."""
    check_rate_limit()

    args = ["apps"]
    result = await execute("steer", args)

    apps = []
    if isinstance(result["output"], list):
        apps = result["output"]
    elif isinstance(result["output"], str):
        apps = [{"name": line.strip()} for line in result["output"].split("\n") if line.strip()]

    log_action(
        node_type="steer_apps",
        command="apps",
        arguments={},
        target="system",
        result=f"Found {len(apps)} apps",
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    return {
        "text": "\n".join(a.get("name", str(a)) if isinstance(a, dict) else str(a) for a in apps),
        "apps": apps,
        "app_count": len(apps),
        "success": result["success"],
    }


# Executor dispatch table
STEER_EXECUTORS = {
    "steer_see": execute_steer_see,
    "steer_ocr": execute_steer_ocr,
    "steer_click": execute_steer_click,
    "steer_type": execute_steer_type,
    "steer_hotkey": execute_steer_hotkey,
    "steer_scroll": execute_steer_scroll,
    "steer_drag": execute_steer_drag,
    "steer_focus": execute_steer_focus,
    "steer_find": execute_steer_find,
    "steer_wait": execute_steer_wait,
    "steer_clipboard": execute_steer_clipboard,
    "steer_apps": execute_steer_apps,
}
