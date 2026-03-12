"""Agent runner service — manages lifecycle of spawned coding agents in tmux sessions."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.config.agent_backends import AgentBackend, get_backend
from app.services.computer_use.executor import execute
from app.services.computer_use.safety import check_rate_limit, log_action

logger = logging.getLogger(__name__)


class AgentRunner:
    """Manages spawning, prompting, monitoring, and capturing external coding agents."""

    async def spawn(
        self,
        backend_name: str,
        session_name: str,
        working_directory: str = "",
        env_vars: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Spawn a coding agent in a new tmux session."""
        check_rate_limit()
        backend = get_backend(backend_name)
        if not backend:
            raise ValueError(f"Unknown agent backend: {backend_name}")

        # Create tmux session
        create_args = ["session", "create", session_name]
        await execute("drive", create_args)

        # Build the launch command
        cmd_parts = [backend.command] + backend.flags
        if working_directory:
            cd_cmd = f"cd {working_directory} && {' '.join(cmd_parts)}"
        else:
            cd_cmd = " ".join(cmd_parts)

        # Add env vars
        if env_vars or backend.env_vars:
            merged = {**backend.env_vars, **(env_vars or {})}
            env_prefix = " ".join(f"{k}={v}" for k, v in merged.items())
            cd_cmd = f"{env_prefix} {cd_cmd}"

        # Send command to tmux session
        send_args = ["send", cd_cmd, "--session", session_name]
        await execute("drive", send_args)
        # Send Enter
        send_enter = ["send", "Enter", "--session", session_name]
        await execute("drive", send_enter)

        log_action(
            node_type="agent_spawn",
            command=f"spawn {backend_name}",
            arguments={"session": session_name, "backend": backend_name, "cwd": working_directory},
            target=session_name,
            result=f"Spawned {backend_name} in {session_name}",
        )

        return {
            "session": session_name,
            "backend": backend_name,
            "command": backend.command,
            "status": "spawned",
        }

    async def prompt(
        self,
        session_name: str,
        task_prompt: str,
        backend_name: str = "",
    ) -> dict[str, Any]:
        """Send a task prompt to a running agent."""
        check_rate_limit()
        backend = get_backend(backend_name) if backend_name else None

        if backend and backend.prompt_method == "stdin":
            # Send via tmux keys (stdin piping)
            send_args = ["send", task_prompt, "--session", session_name]
            await execute("drive", send_args)
            send_enter = ["send", "Enter", "--session", session_name]
            await execute("drive", send_enter)
        else:
            # Send as typed text
            send_args = ["send", task_prompt, "--session", session_name]
            await execute("drive", send_args)
            send_enter = ["send", "Enter", "--session", session_name]
            await execute("drive", send_enter)

        log_action(
            node_type="agent_prompt",
            command="prompt",
            arguments={"session": session_name, "prompt_length": len(task_prompt)},
            target=session_name,
            result=f"Sent prompt ({len(task_prompt)} chars)",
        )

        return {"session": session_name, "prompt_sent": True, "prompt_length": len(task_prompt)}

    async def monitor(
        self,
        session_name: str,
        lines: int = 100,
    ) -> dict[str, Any]:
        """Capture current output from a running agent's tmux pane."""
        check_rate_limit()
        args = ["logs", "--session", session_name, "--lines", str(lines)]
        result = await execute("drive", args)
        output = str(result.get("output", ""))

        return {
            "session": session_name,
            "output": output,
            "line_count": output.count("\n") + 1 if output else 0,
        }

    async def wait_for_completion(
        self,
        session_name: str,
        backend_name: str = "",
        timeout: int = 300,
        poll_interval: int = 5,
        completion_pattern: str = "",
    ) -> dict[str, Any]:
        """Wait for the agent to finish its task using completion detection."""
        backend = get_backend(backend_name) if backend_name else None
        pattern = completion_pattern or (backend.completion_pattern if backend else r">\s*$")
        compiled = re.compile(pattern)

        elapsed = 0
        last_output = ""

        while elapsed < timeout:
            result = await self.monitor(session_name)
            current_output = result["output"]

            # Check if output matches completion pattern
            lines = current_output.strip().split("\n")
            if lines:
                last_line = lines[-1].strip()
                if compiled.search(last_line) and current_output != last_output and elapsed > 2:
                    log_action(
                        node_type="agent_wait",
                        command="wait_completed",
                        arguments={"session": session_name, "elapsed": elapsed},
                        target=session_name,
                        result=f"Agent completed after {elapsed}s",
                    )
                    return {
                        "session": session_name,
                        "completed": True,
                        "elapsed_seconds": elapsed,
                        "output": current_output,
                    }

            last_output = current_output
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        return {
            "session": session_name,
            "completed": False,
            "elapsed_seconds": elapsed,
            "output": last_output,
            "timed_out": True,
        }

    async def capture_result(
        self,
        session_name: str,
        output_format: str = "text",
        lines: int = 500,
    ) -> dict[str, Any]:
        """Capture the full output from a completed agent session."""
        result = await self.monitor(session_name, lines=lines)
        output = result["output"]

        parsed: Any = output
        if output_format == "json":
            import json
            try:
                # Try to extract JSON from output
                json_match = re.search(r'\{[\s\S]*\}', output)
                if json_match:
                    parsed = json.loads(json_match.group())
            except (json.JSONDecodeError, AttributeError):
                parsed = output

        log_action(
            node_type="agent_result",
            command="capture",
            arguments={"session": session_name, "format": output_format},
            target=session_name,
            result=f"Captured {len(output)} chars",
        )

        return {
            "session": session_name,
            "output": output,
            "parsed": parsed,
            "format": output_format,
            "length": len(output),
        }

    async def stop(self, session_name: str) -> dict[str, Any]:
        """Stop a running agent and clean up the tmux session."""
        check_rate_limit()
        # Send Ctrl-C first to try graceful stop
        try:
            send_args = ["send", "C-c", "--session", session_name]
            await execute("drive", send_args)
            await asyncio.sleep(1)
        except Exception:
            pass

        # Kill the tmux session
        try:
            kill_args = ["session", "kill", session_name]
            await execute("drive", kill_args)
        except Exception:
            pass

        log_action(
            node_type="agent_stop",
            command="stop",
            arguments={"session": session_name},
            target=session_name,
            result=f"Stopped and cleaned up {session_name}",
        )

        return {"session": session_name, "stopped": True}

    async def status(self, session_name: str) -> dict[str, Any]:
        """Check current state of a spawned agent."""
        try:
            result = await self.monitor(session_name, lines=5)
            return {
                "session": session_name,
                "alive": True,
                "last_output": result["output"],
            }
        except Exception:
            return {
                "session": session_name,
                "alive": False,
                "last_output": "",
            }


agent_runner = AgentRunner()
