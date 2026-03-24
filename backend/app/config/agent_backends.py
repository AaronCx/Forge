"""Agent backend configuration — pre-configured and custom coding agent CLIs."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentBackend:
    """Definition of an external coding agent that Forge can spawn and control."""

    name: str
    command: str
    prompt_method: str  # "argument", "stdin", or "file"
    output_capture: str  # "tmux" or "file"
    completion_pattern: str  # regex pattern to detect idle/completed state
    env_vars: dict[str, str] = field(default_factory=dict)
    description: str = ""
    flags: list[str] = field(default_factory=list)
    output_format: str = "text"  # "text" or "json"


# Pre-configured agent backends
BUILTIN_BACKENDS: dict[str, AgentBackend] = {
    "claude-code": AgentBackend(
        name="claude-code",
        command="claude",
        prompt_method="argument",
        output_capture="tmux",
        completion_pattern=r"(╭─|>\s*$|\$\s*$)",
        description="Anthropic Claude Code — autonomous coding agent with file editing and tool use.",
        flags=["--dangerously-skip-permissions"],
        output_format="text",
    ),
    "codex-cli": AgentBackend(
        name="codex-cli",
        command="codex",
        prompt_method="argument",
        output_capture="tmux",
        completion_pattern=r"(>\s*$|\$\s*$|codex>)",
        description="OpenAI Codex CLI — code generation and editing agent.",
    ),
    "gemini-cli": AgentBackend(
        name="gemini-cli",
        command="gemini",
        prompt_method="argument",
        output_capture="tmux",
        completion_pattern=r"(>\s*$|\$\s*$)",
        description="Google Gemini CLI — multimodal coding agent.",
    ),
    "aider": AgentBackend(
        name="aider",
        command="aider",
        prompt_method="stdin",
        output_capture="tmux",
        completion_pattern=r"(aider>\s*$|>\s*$)",
        description="Aider — AI pair programming in your terminal.",
        flags=["--yes-always"],
    ),
}


def get_backend(name: str) -> AgentBackend | None:
    """Look up a backend by name (builtin or custom from env)."""
    if name in BUILTIN_BACKENDS:
        return BUILTIN_BACKENDS[name]
    # Check for custom backend from environment
    prefix = f"AF_AGENT_BACKEND_{name.upper().replace('-', '_')}"
    cmd = os.getenv(f"{prefix}_COMMAND")
    if cmd:
        return AgentBackend(
            name=name,
            command=cmd,
            prompt_method=os.getenv(f"{prefix}_PROMPT_METHOD", "argument"),
            output_capture=os.getenv(f"{prefix}_OUTPUT_CAPTURE", "tmux"),
            completion_pattern=os.getenv(f"{prefix}_COMPLETION_PATTERN", r">\s*$"),
            description=os.getenv(f"{prefix}_DESCRIPTION", f"Custom agent: {name}"),
        )
    return None


def list_backends() -> list[dict[str, Any]]:
    """List all available backends."""
    result = []
    for b in BUILTIN_BACKENDS.values():
        result.append({
            "name": b.name,
            "command": b.command,
            "prompt_method": b.prompt_method,
            "description": b.description,
            "builtin": True,
        })
    return result
