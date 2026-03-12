"""Drive node executors — terminal automation via Drive CLI and tmux."""

from __future__ import annotations

import uuid
from typing import Any

from app.services.computer_use.executor import execute
from app.services.computer_use.safety import (
    check_command_blocklist,
    check_rate_limit,
    log_action,
)


async def execute_drive_session(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Create, list, or manage tmux sessions."""
    check_rate_limit()
    action = config.get("action", "create")
    session_name = config.get("session") or config.get("session_name") or inputs.get("session", "")

    if action == "create":
        if not session_name:
            session_name = f"af-{uuid.uuid4().hex[:8]}"
        args = ["session", "create", session_name]
        layout = config.get("layout")
        if layout:
            args.extend(["--layout", layout])
    elif action == "list":
        args = ["session", "list"]
    elif action == "kill":
        if not session_name:
            raise ValueError("drive_session kill: 'session' name is required")
        args = ["session", "kill", session_name]
    else:
        raise ValueError(f"drive_session: unknown action '{action}' (use create/list/kill)")

    result = await execute("drive", args)

    sessions = []
    if action == "list":
        if isinstance(result["output"], list):
            sessions = result["output"]
        elif isinstance(result["output"], str):
            sessions = [s.strip() for s in result["output"].split("\n") if s.strip()]

    log_action(
        node_type="drive_session",
        command=f"session {action}",
        arguments={"action": action, "session": session_name},
        target=session_name or "all",
        result=str(result["output"])[:500],
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    return {
        "text": f"Session {action}: {session_name or 'listed'}",
        "session": session_name,
        "sessions": sessions,
        "action": action,
        "success": result["success"],
    }


async def execute_drive_run(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Execute a command in a tmux pane with sentinel pattern."""
    check_rate_limit()
    session = config.get("session") or inputs.get("session", "")
    command = config.get("command") or inputs.get("command", "")
    timeout = int(config.get("timeout", 30))

    if not command:
        raise ValueError("drive_run: 'command' is required")

    check_command_blocklist(command)

    args = ["run", command]
    if session:
        args.extend(["--session", session])
    args.extend(["--timeout", str(timeout)])

    result = await execute("drive", args, timeout=timeout + 10)

    exit_code = result.get("exit_code", -1)
    output = result.get("output", "")
    if isinstance(output, dict):
        exit_code = output.get("exit_code", exit_code)
        output = output.get("output", str(output))

    log_action(
        node_type="drive_run",
        command=command,
        arguments={"session": session, "timeout": timeout},
        target=session or "default",
        result=str(output)[:1000],
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    return {
        "text": str(output),
        "command": command,
        "exit_code": exit_code,
        "session": session,
        "success": result["success"],
    }


async def execute_drive_send(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Send raw keystrokes to a tmux pane."""
    check_rate_limit()
    session = config.get("session") or inputs.get("session", "")
    keys = config.get("keys") or inputs.get("keys", "")

    if not keys:
        raise ValueError("drive_send: 'keys' is required")

    args = ["send", keys]
    if session:
        args.extend(["--session", session])

    result = await execute("drive", args)

    log_action(
        node_type="drive_send",
        command="send",
        arguments={"keys": keys[:100], "session": session},
        target=session or "default",
        result="sent" if result["success"] else str(result["output"]),
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    return {
        "text": f"Sent keys to {session or 'default'}",
        "success": result["success"],
    }


async def execute_drive_logs(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Capture the current output of a tmux pane."""
    check_rate_limit()
    session = config.get("session") or inputs.get("session", "")
    lines = int(config.get("lines", 100))

    args = ["logs"]
    if session:
        args.extend(["--session", session])
    args.extend(["--lines", str(lines)])

    result = await execute("drive", args)

    output = str(result.get("output", ""))

    log_action(
        node_type="drive_logs",
        command="logs",
        arguments={"session": session, "lines": lines},
        target=session or "default",
        result=f"Captured {len(output)} chars",
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    return {
        "text": output,
        "session": session,
        "line_count": output.count("\n") + 1 if output else 0,
        "success": result["success"],
    }


async def execute_drive_poll(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Wait for a sentinel marker indicating command completion."""
    check_rate_limit()
    session = config.get("session") or inputs.get("session", "")
    token = config.get("token") or inputs.get("token", "")
    timeout = int(config.get("timeout", 30))

    if not token:
        raise ValueError("drive_poll: 'token' (sentinel to watch for) is required")

    args = ["poll", token]
    if session:
        args.extend(["--session", session])
    args.extend(["--timeout", str(timeout)])

    result = await execute("drive", args, timeout=timeout + 5)

    output = result.get("output", "")
    exit_code = -1
    if isinstance(output, dict):
        exit_code = output.get("exit_code", -1)
        output = output.get("output", str(output))

    log_action(
        node_type="drive_poll",
        command="poll",
        arguments={"token": token, "session": session, "timeout": timeout},
        target=session or "default",
        result=f"exit_code={exit_code}" if result["success"] else "timed out",
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    return {
        "text": str(output),
        "exit_code": exit_code,
        "completed": result["success"],
        "session": session,
        "success": result["success"],
    }


async def execute_drive_fanout(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Execute commands across multiple tmux panes in parallel."""
    check_rate_limit()
    session = config.get("session") or inputs.get("session", "")
    commands = config.get("commands", [])
    layout = config.get("layout", "tiled")

    if not commands:
        raise ValueError("drive_fanout: 'commands' array is required")

    for cmd in commands:
        check_command_blocklist(cmd)

    args = ["fanout"]
    if session:
        args.extend(["--session", session])
    args.extend(["--layout", layout])
    for cmd in commands:
        args.extend(["--command", cmd])

    result = await execute("drive", args, timeout=60)

    results = []
    if isinstance(result["output"], list):
        results = result["output"]
    elif isinstance(result["output"], dict):
        results = result["output"].get("results", [result["output"]])
    else:
        results = [{"output": str(result["output"]), "exit_code": result.get("exit_code", 0)}]

    log_action(
        node_type="drive_fanout",
        command="fanout",
        arguments={"commands": commands, "session": session, "layout": layout},
        target=session or "default",
        result=f"Ran {len(commands)} commands",
        user_id=inputs.get("_user_id", ""),
        run_id=inputs.get("_run_id", ""),
        success=result["success"],
    )

    combined_text = "\n---\n".join(
        str(r.get("output", r) if isinstance(r, dict) else r)
        for r in results
    )

    return {
        "text": combined_text,
        "results": results,
        "command_count": len(commands),
        "session": session,
        "success": result["success"],
    }


# Executor dispatch table
DRIVE_EXECUTORS = {
    "drive_session": execute_drive_session,
    "drive_run": execute_drive_run,
    "drive_send": execute_drive_send,
    "drive_logs": execute_drive_logs,
    "drive_poll": execute_drive_poll,
    "drive_fanout": execute_drive_fanout,
}
