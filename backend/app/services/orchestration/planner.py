"""The workflow planner (Phase 9.2).

Given a goal and a capability inventory (tool names + descriptions from the
ToolPlane, available ModelCards, dispatch targets), the *session's* model
returns a ``WorkflowSpec``. The prompt template lives in the existing
prompt-versioning system as ``planner/v1`` (agent id ``__planner__<user>``) so
it is diffable, rollback-able, and eval-able like any other prompt.

Fan-out stages default to the cheapest tools-capable ModelCard
(``worker_model``) so they do not burn flagship tokens; the planner itself
always runs on the session's model.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from typing import Any

from app.kernel.models import load_model_cards
from app.kernel.serialize import workflow_spec_from_dict, workflow_spec_json_schema
from app.kernel.toolplane import ExecContext, tool_plane
from app.kernel.types import (
    KMessage,
    SubAgentSpec,
    TextBlock,
    WorkflowSpec,
    WorkflowStage,
)

logger = logging.getLogger(__name__)

PLANNER_AGENT_PREFIX = "__planner__"
_DEFAULT_AGENT_TOKENS = 30_000  # rough per-agent estimate when no budget given

PLANNER_TEMPLATE_V1 = """\
You are Forge's workflow planner. Decompose the user's goal into a workflow of
scoped sub-agents and answer with ONE JSON object matching the WorkflowSpec
schema below — no prose, no code fences.

Rules:
- Prefer a fan-out stage of small, independent agents over one big agent when
  the goal decomposes (per file, per item, per source). Give every agent a
  narrow tools allowlist from the inventory (or "inherit"), a precise prompt,
  and a testable success_criteria.
- Unless the goal is trivial, end with a stage of kind "verify" that depends on
  the producing stages: an adversarial reviewer that judges each producer's
  output against its success_criteria. Never let a producer judge itself.
- Use "reduce" for a final synthesis stage when results must be merged.
- Leave "model" null on agents unless a stage truly needs a specific model;
  cheap fan-out work runs on worker_model automatically.
- Set "target" on a stage only when it must run on a named dispatch machine.
- Keep max_agents_total honest — it is a hard ceiling, not an aspiration.

Goal:
{{goal}}

Available tools (name — description):
{{tools}}

Available models (id, provider, vision/tools flags, price per 1M tokens in/out):
{{models}}

Dispatch targets (machines a stage's "target" may name):
{{targets}}

WorkflowSpec JSON schema:
{{schema}}
"""


async def _ensure_planner_template(user_id: str) -> str:
    """Return the active planner template, seeding planner/v1 on first use."""
    from app.db import get_db
    from app.services.observability.prompt_versions import prompt_version_service

    agent_id = f"{PLANNER_AGENT_PREFIX}{user_id}"
    active = await prompt_version_service.get_active_version(agent_id, user_id)
    if active:
        return str(active["system_prompt"])

    # prompt_versions.agent_id references agents(id): keep a system-managed
    # agent row holding the template so versioning/rollback work unchanged.
    db = get_db()
    existing = db.table("agents").select("id").eq("id", agent_id).execute()
    if not (existing.data or []):
        db.table("agents").insert({
            "id": agent_id,
            "user_id": user_id,
            "name": "Workflow Planner",
            "description": "System agent holding the workflow planner prompt template.",
            "system_prompt": PLANNER_TEMPLATE_V1,
            "ephemeral": 1,
        }).execute()
    await prompt_version_service.create_version(
        user_id=user_id, agent_id=agent_id,
        system_prompt=PLANNER_TEMPLATE_V1, change_summary="planner/v1 (seeded)",
    )
    return PLANNER_TEMPLATE_V1


async def build_inventory(user_id: str, ctx: ExecContext) -> dict[str, str]:
    """The capability inventory the planner reasons over."""
    specs = await tool_plane.list_tools(user_id, ctx)
    tools = "\n".join(
        f"- {s.name} — {s.description}" + (" [dangerous]" if s.danger_level == "dangerous" else "")
        for s in specs
    )

    cards = load_model_cards()
    models = "\n".join(
        f"- {c.id} ({c.provider}; vision={c.vision}, tools={c.tools}, "
        f"${c.input_price_per_1m or '?'}/{c.output_price_per_1m or '?'})"
        for c in cards.values()
    )

    targets = "(none registered)"
    try:
        from app.db import get_db

        rows = (
            get_db().table("execution_targets").select("name, platform, status")
            .eq("user_id", user_id).execute().data or []
        )
        if rows:
            targets = "\n".join(
                f"- {r['name']} ({r.get('platform', '?')}, {r.get('status', 'unknown')})"
                for r in rows
            )
    except Exception:  # noqa: BLE001 - targets are optional context
        logger.debug("target inventory failed", exc_info=True)

    return {"tools": tools, "models": models, "targets": targets}


def cheapest_worker_model() -> str | None:
    """The cheapest tools-capable ModelCard — the default fan-out model."""
    cards = load_model_cards()
    priced = [
        c for c in cards.values()
        if c.tools and c.input_price_per_1m is not None and c.output_price_per_1m is not None
    ]
    if not priced:
        return None
    best = min(priced, key=lambda c: (c.input_price_per_1m or 0) + (c.output_price_per_1m or 0))
    return str(best.id)


def _parse_spec(raw_text: str) -> WorkflowSpec:
    """Parse the planner's reply into a WorkflowSpec (tolerates code fences)."""
    text = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("planner returned no JSON object")
    data = json.loads(text[start:end + 1])
    spec = workflow_spec_from_dict(data)
    if not spec.stages:
        raise ValueError("planner returned a workflow with no stages")
    return spec


def ensure_verify_stage(spec: WorkflowSpec, goal: str = "") -> WorkflowSpec:
    """Append a default verify stage unless the spec opted out or has one.

    The reviewer receives the goal, every producer's success_criteria, and
    their outputs, and returns a pass/fail verdict with findings per item
    (Phase 9.4) — the judge never wrote the answers it judges.
    """
    if not spec.verify or any(st.kind == "verify" for st in spec.stages):
        return spec
    depended_on = {dep for st in spec.stages for dep in st.depends_on}
    terminal = [st.id for st in spec.stages if st.id not in depended_on]
    if not terminal:
        return spec
    reviewer = SubAgentSpec(
        role="reviewer",
        prompt=(
            "You are an adversarial reviewer. Judge each producer's output "
            "strictly against its success criteria"
            + (f" in service of the goal: {goal.strip()}" if goal.strip() else "")
            + ". Look for unmet criteria, unsupported claims, and missing "
            "coverage — do not rubber-stamp."
        ),
        tools=[],
        success_criteria="Every item receives an explicit pass/fail verdict with findings.",
    )
    stage = WorkflowStage(id="verify", kind="verify", agents=[reviewer],
                          depends_on=terminal)
    return dataclasses.replace(spec, stages=[*spec.stages, stage])


def estimate_tokens(spec: WorkflowSpec) -> int:
    """A rough token estimate for the consent card, from agent budgets."""
    total = 0
    for stage in spec.stages:
        for agent in stage.agents:
            budget = agent.budget.max_tokens if agent.budget else None
            total += budget or _DEFAULT_AGENT_TOKENS
    return total


async def plan_workflow(
    goal: str,
    *,
    user_id: str,
    model: str | None,
    registry: Any,
    ctx: ExecContext,
) -> WorkflowSpec:
    """Ask the session's model for a WorkflowSpec for ``goal``."""
    template = await _ensure_planner_template(user_id)
    inventory = await build_inventory(user_id, ctx)
    prompt = (
        template.replace("{{goal}}", goal.strip())
        .replace("{{tools}}", inventory["tools"])
        .replace("{{models}}", inventory["models"])
        .replace("{{targets}}", inventory["targets"])
        .replace("{{schema}}", json.dumps(workflow_spec_json_schema(), indent=2))
    )
    messages = [
        KMessage(role="system", blocks=[TextBlock(prompt)]),
        KMessage(role="user", blocks=[TextBlock(goal.strip())]),
    ]
    turn = await registry.turn(messages, model)
    spec = _parse_spec(turn.text)
    if spec.worker_model is None:
        worker = cheapest_worker_model()
        if worker:
            spec = dataclasses.replace(spec, worker_model=worker)
    return ensure_verify_stage(spec, goal)


async def plan_for_context(goal: str, ctx: ExecContext) -> WorkflowSpec:
    """Planner entry point for the ``orchestrate.plan`` tool."""
    from app.providers.registry import create_user_registry, provider_registry

    model: str | None = None
    if ctx.session_id:
        from app.db import get_db

        rows = (
            get_db().table("sessions").select("model").eq("id", ctx.session_id)
            .execute().data or []
        )
        if rows:
            model = rows[0].get("model") or None
    registry = await create_user_registry(ctx.user_id) or provider_registry
    return await plan_workflow(
        goal, user_id=ctx.user_id, model=model, registry=registry, ctx=ctx
    )
