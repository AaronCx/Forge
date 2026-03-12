"""Agent-on-agent node executors — spawn, prompt, monitor, wait, stop, capture results."""

from __future__ import annotations

import uuid
from typing import Any

from app.services.computer_use.agents.agent_runner import agent_runner
from app.services.computer_use.safety import check_rate_limit, log_action


async def execute_agent_spawn(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Spawn a coding agent in a new tmux session."""
    check_rate_limit()
    backend = config.get("backend") or inputs.get("backend", "claude-code")
    session = config.get("session") or inputs.get("session", "")
    working_dir = config.get("working_directory") or inputs.get("working_directory", "")
    env_vars = config.get("env_vars") or inputs.get("env_vars", {})

    if not session:
        session = f"af-agent-{uuid.uuid4().hex[:8]}"

    result = await agent_runner.spawn(
        backend_name=backend,
        session_name=session,
        working_directory=working_dir,
        env_vars=env_vars if isinstance(env_vars, dict) else {},
    )

    return {
        "text": f"Spawned {backend} in session {session}",
        "session": result["session"],
        "backend": result["backend"],
        "status": result["status"],
        "success": True,
    }


async def execute_agent_prompt(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Send a task prompt to a running agent."""
    check_rate_limit()
    session = config.get("session") or inputs.get("session", "")
    prompt = config.get("prompt") or inputs.get("prompt", "")
    backend = config.get("backend") or inputs.get("backend", "")

    if not session:
        raise ValueError("agent_prompt: 'session' is required")
    if not prompt:
        raise ValueError("agent_prompt: 'prompt' is required")

    result = await agent_runner.prompt(
        session_name=session,
        task_prompt=prompt,
        backend_name=backend,
    )

    return {
        "text": f"Sent prompt to {session} ({result['prompt_length']} chars)",
        "session": result["session"],
        "prompt_sent": result["prompt_sent"],
        "prompt_length": result["prompt_length"],
        "success": True,
    }


async def execute_agent_monitor(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Capture the current output of a running agent."""
    check_rate_limit()
    session = config.get("session") or inputs.get("session", "")
    lines = int(config.get("lines", 100))

    if not session:
        raise ValueError("agent_monitor: 'session' is required")

    result = await agent_runner.monitor(session_name=session, lines=lines)

    return {
        "text": result["output"],
        "session": result["session"],
        "line_count": result["line_count"],
        "success": True,
    }


async def execute_agent_wait(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Wait for a spawned agent to complete its task."""
    check_rate_limit()
    session = config.get("session") or inputs.get("session", "")
    backend = config.get("backend") or inputs.get("backend", "")
    timeout = int(config.get("timeout", 300))
    poll_interval = int(config.get("poll_interval", 5))
    completion_pattern = config.get("completion_pattern") or ""

    if not session:
        raise ValueError("agent_wait: 'session' is required")

    result = await agent_runner.wait_for_completion(
        session_name=session,
        backend_name=backend,
        timeout=timeout,
        poll_interval=poll_interval,
        completion_pattern=completion_pattern,
    )

    return {
        "text": result["output"],
        "session": result["session"],
        "completed": result["completed"],
        "elapsed_seconds": result["elapsed_seconds"],
        "timed_out": result.get("timed_out", False),
        "success": result["completed"],
    }


async def execute_agent_stop(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Stop a running agent and clean up."""
    check_rate_limit()
    session = config.get("session") or inputs.get("session", "")

    if not session:
        raise ValueError("agent_stop: 'session' is required")

    result = await agent_runner.stop(session_name=session)

    return {
        "text": f"Stopped agent in session {session}",
        "session": result["session"],
        "stopped": result["stopped"],
        "success": True,
    }


async def execute_agent_result(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Extract and parse the final result from a completed agent session."""
    check_rate_limit()
    session = config.get("session") or inputs.get("session", "")
    output_format = config.get("output_format") or inputs.get("output_format", "text")
    lines = int(config.get("lines", 500))

    if not session:
        raise ValueError("agent_result: 'session' is required")

    result = await agent_runner.capture_result(
        session_name=session,
        output_format=output_format,
        lines=lines,
    )

    return {
        "text": result["output"],
        "parsed": result["parsed"],
        "format": result["format"],
        "length": result["length"],
        "session": result["session"],
        "success": True,
    }


# Executor dispatch table
AGENT_CONTROL_EXECUTORS = {
    "agent_spawn": execute_agent_spawn,
    "agent_prompt": execute_agent_prompt,
    "agent_monitor": execute_agent_monitor,
    "agent_wait": execute_agent_wait,
    "agent_stop": execute_agent_stop,
    "agent_result": execute_agent_result,
}
