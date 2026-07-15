"""WorkflowSpec → blueprint compiler (Phase 9.3).

Compiles a planner-produced ``WorkflowSpec`` into a blueprint dict the existing
DAG engine executes unchanged. Each ``SubAgentSpec`` becomes an *ephemeral*
agent row (auditable, dashboard-visible behind a filter, garbage-collectible)
and one ``subagent_run`` node; ``fanout`` stages compile to N parallel nodes in
one topological layer. ``max_agents_total`` is a hard ceiling that aborts
compilation — never execution.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import uuid
from dataclasses import asdict
from typing import Any

from app.kernel.types import SubAgentSpec, WorkflowSpec, WorkflowStage

logger = logging.getLogger(__name__)


class WorkflowCompileError(ValueError):
    """The spec cannot be compiled (bad DAG, agent ceiling, empty stages)."""


def _create_ephemeral_agent(
    user_id: str,
    session_id: str,
    spec: WorkflowSpec,
    stage: WorkflowStage,
    agent: SubAgentSpec,
) -> str:
    """Persist one sub-agent as an ephemeral ``agents`` row; returns its id."""
    from app.db import get_db

    agent_id = str(uuid.uuid4())
    row: dict[str, Any] = {
        "id": agent_id,
        "user_id": user_id,
        "name": f"{spec.title} — {stage.id}/{agent.role}",
        "description": f"Ephemeral sub-agent spawned for workflow '{spec.title}'.",
        "system_prompt": agent.prompt,
        "agent_role": "worker",
        "ephemeral": 1,
        "spawned_by_session": session_id or None,
        "spec_json": json.dumps(asdict(agent), default=str),
    }
    try:
        get_db().table("agents").insert(row).execute()
    except Exception:  # noqa: BLE001 - auditing row must not block compilation
        logger.warning("ephemeral agent insert failed for %s", agent_id, exc_info=True)
    return agent_id


def compile_workflow(
    spec: WorkflowSpec,
    *,
    user_id: str,
    session_id: str = "",
    policy: dict[str, Any] | None = None,
    workspace_root: str = "",
    create_agents: bool = True,
) -> dict[str, Any]:
    """Compile a WorkflowSpec into a blueprint dict for ``blueprint_engine``.

    Raises ``WorkflowCompileError`` on an invalid spec. The returned blueprint
    is self-contained: node configs carry each sub-agent's spec, the worker
    model, the concurrency limit, and the parent's permission policy.
    """
    if not spec.stages:
        raise WorkflowCompileError("workflow has no stages")
    if spec.agent_count == 0:
        raise WorkflowCompileError("workflow has no agents")
    if spec.agent_count > spec.max_agents_total:
        raise WorkflowCompileError(
            f"workflow would spawn {spec.agent_count} agents, over the "
            f"max_agents_total ceiling of {spec.max_agents_total}"
        )

    # A sub-agent whose role names a saved agent template inherits that
    # template's system prompt (Phase 9.6 — templates gain a purpose).
    try:
        from app.services.orchestration.planner import load_agent_templates

        templates = load_agent_templates(user_id)
    except Exception:  # noqa: BLE001 - templates are optional
        templates = {}

    seen_stages: set[str] = set()
    stage_nodes: dict[str, list[str]] = {}
    nodes: list[dict[str, Any]] = []

    for stage in spec.stages:
        if not stage.id:
            raise WorkflowCompileError("every stage needs an id")
        if stage.id in seen_stages:
            raise WorkflowCompileError(f"duplicate stage id '{stage.id}'")
        seen_stages.add(stage.id)

        deps: list[str] = []
        for dep in stage.depends_on:
            if dep not in stage_nodes:
                raise WorkflowCompileError(
                    f"stage '{stage.id}' depends on unknown stage '{dep}'"
                )
            deps.extend(stage_nodes[dep])

        agents = list(stage.agents)
        if not agents:
            raise WorkflowCompileError(f"stage '{stage.id}' has no agents")
        if stage.kind != "fanout" and len(agents) > 1:
            raise WorkflowCompileError(
                f"stage '{stage.id}' is kind '{stage.kind}' but has "
                f"{len(agents)} agents — only fanout stages may have several"
            )

        concurrency = stage.concurrency or spec.max_concurrent
        node_ids: list[str] = []
        for i, agent in enumerate(agents):
            if agent.role in templates:
                _desc, template_prompt = templates[agent.role]
                if template_prompt:
                    agent = dataclasses.replace(
                        agent,
                        prompt=f"{template_prompt}\n\n{agent.prompt}".strip(),
                    )
            node_id = stage.id if len(agents) == 1 else f"{stage.id}-{i + 1}"
            # Saving a workflow to the library compiles without spawning
            # audit rows; a fresh run re-creates them.
            agent_row_id = (
                _create_ephemeral_agent(user_id, session_id, spec, stage, agent)
                if create_agents else ""
            )
            nodes.append({
                "id": node_id,
                "type": "subagent_run",
                "label": f"{stage.id}: {agent.role}",
                "dependencies": deps,
                "config": {
                    "spec": asdict(agent),
                    "agent_id": agent_row_id,
                    "stage_id": stage.id,
                    "stage_kind": stage.kind,
                    "worker_model": spec.worker_model,
                    "max_concurrent": min(concurrency, spec.max_concurrent),
                    "workflow_title": spec.title,
                    "session_id": session_id,
                    "policy": dict(policy or {}),
                    "workspace_root": workspace_root,
                    "target": stage.target,
                },
            })
            node_ids.append(node_id)
        stage_nodes[stage.id] = node_ids

    return {
        "name": spec.title,
        "description": spec.rationale,
        "nodes": nodes,
        "context_config": {},
        "retry_policy": {"max_retries": 1},
        "workflow_spec": asdict(spec),  # provenance for save/rerun/fork
    }
