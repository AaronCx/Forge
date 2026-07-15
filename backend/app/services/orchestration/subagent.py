"""The ``subagent_run`` node executor (Phase 9.3) — registry entry 45.

Runs one scoped sub-agent through the kernel loop: its own message list seeded
from the spec's ``inputs`` (plus upstream DAG context), the spec's tool
allowlist resolved through the ToolPlane, its own ``Budget``, and the parent's
permission policy — inherited, never elevated. The return value is the node
output, so intermediate state lives in DAG edges, not the parent context.

A per-run semaphore honors the workflow's ``max_concurrent``; sub-agents never
receive ``orchestrate.plan`` or ``node.subagent_run`` (no recursive fan-out).

``config["target"]`` (a dispatch machine) is recorded in the audit trail; the
node itself executes locally — remote dispatch keeps flowing through the
existing ``agent.*`` / dispatch tools a sub-agent may call.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.kernel.loop import Budget, run_agent_turn
from app.kernel.toolplane import ExecContext, tool_plane
from app.kernel.types import KMessage, TextBlock, TurnDone

logger = logging.getLogger(__name__)

# Tools a sub-agent must never see, regardless of allowlist/inherit.
_FORBIDDEN_SUBAGENT_TOOLS = {"orchestrate.plan", "node.subagent_run"}

_MAX_SUBAGENT_ITERATIONS = 12

# Per-run fan-out semaphores (created on first use with the run's limit).
_RUN_SEMAPHORES: dict[str, asyncio.Semaphore] = {}


def _run_semaphore(run_id: str, limit: int) -> asyncio.Semaphore:
    sem = _RUN_SEMAPHORES.get(run_id)
    if sem is None:
        sem = asyncio.Semaphore(max(1, limit))
        _RUN_SEMAPHORES[run_id] = sem
    return sem


def release_run(run_id: str) -> None:
    """Drop the semaphore for a finished workflow run."""
    _RUN_SEMAPHORES.pop(run_id, None)


def _system_prompt(spec: dict[str, Any], config: dict[str, Any]) -> str:
    parts = [
        f"You are a scoped sub-agent (role: {spec.get('role', 'worker')}) inside "
        f"the workflow '{config.get('workflow_title', 'workflow')}'.",
        str(spec.get("prompt", "")).strip(),
    ]
    criteria = str(spec.get("success_criteria", "")).strip()
    if criteria:
        parts.append(f"Your output will be judged against: {criteria}")
    parts.append(
        "Work only on your assigned scope. Return your result directly as your "
        "final message — it becomes this node's output."
    )
    return "\n\n".join(p for p in parts if p)


def _user_prompt(spec: dict[str, Any], inputs: dict[str, Any]) -> str:
    parts: list[str] = []
    declared = spec.get("inputs")
    if isinstance(declared, dict) and declared:
        parts.append("Inputs:\n" + json.dumps(declared, indent=2, default=str))
    upstream = inputs.get("text")
    if upstream:
        parts.append(f"Upstream context:\n{upstream}")
    outputs = spec.get("outputs")
    if isinstance(outputs, list) and outputs:
        parts.append("Produce these outputs: " + ", ".join(str(o) for o in outputs))
    return "\n\n".join(parts) or "Begin."


async def execute_subagent_run(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Execute one sub-agent and return its result as the node output."""
    from app.providers.registry import create_user_registry, provider_registry

    spec: dict[str, Any] = config.get("spec") or {}
    user_id = inputs.get("_user_id", "")
    run_id = inputs.get("_run_id", "")
    node_id = inputs.get("_node_id", "")

    model = spec.get("model") or config.get("worker_model") or None

    policy = dict(config.get("policy") or {})
    scope = policy.pop("approve_scope", "tool")
    ctx = ExecContext(
        user_id=user_id,
        run_id=run_id,
        session_id=str(config.get("session_id", "")),
        workspace_root=str(config.get("workspace_root", "")),
        session_overrides=policy,  # inherit the parent's policy, never elevate
        approve_scope=scope if scope in ("call", "tool", "session") else "tool",
    )

    all_specs = await tool_plane.list_tools(user_id, ctx)
    allow = spec.get("tools", "inherit")
    if isinstance(allow, list):
        allowed_names = set(allow)
        tools = [s for s in all_specs if s.name in allowed_names]
    else:
        tools = list(all_specs)
    tools = [s for s in tools if s.name not in _FORBIDDEN_SUBAGENT_TOOLS]

    budget_spec = spec.get("budget") or {}
    budget = Budget(
        max_tokens=budget_spec.get("max_tokens"),
        max_seconds=budget_spec.get("max_seconds"),
    )

    messages = [
        KMessage(role="system", blocks=[TextBlock(_system_prompt(spec, config))]),
        KMessage(role="user", blocks=[TextBlock(_user_prompt(spec, inputs))]),
    ]

    registry = await create_user_registry(user_id) or provider_registry

    input_tokens = 0
    output_tokens = 0
    final_text = ""
    sem = _run_semaphore(run_id or "adhoc", int(config.get("max_concurrent", 16) or 16))
    async with sem:
        async for ev in run_agent_turn(
            messages, tools or None, model,
            registry=registry, plane=tool_plane, ctx=ctx, budget=budget,
            max_iterations=_MAX_SUBAGENT_ITERATIONS,
        ):
            if isinstance(ev, TurnDone):
                input_tokens += ev.turn.usage.input_tokens
                output_tokens += ev.turn.usage.output_tokens
                if ev.turn.stop_reason != "tool_use":
                    final_text = ev.turn.text

    logger.info(
        "subagent %s (%s) finished: %d tools, %d tokens (run=%s target=%s)",
        node_id, spec.get("role", "worker"), len(tools),
        input_tokens + output_tokens, run_id, config.get("target") or "local",
    )

    result: dict[str, Any] = {
        "text": final_text,
        "role": spec.get("role", "worker"),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "agent_id": config.get("agent_id", ""),
    }
    if node_id:
        # A uniquely-keyed copy so downstream verify/reduce stages can tell
        # producers apart after the engine's fan-in merge.
        result[f"result_{node_id}"] = {
            "node_id": node_id,
            "role": result["role"],
            "text": final_text,
            "success_criteria": spec.get("success_criteria", ""),
        }
    return result


SUBAGENT_EXECUTORS = {
    "subagent_run": execute_subagent_run,
}
