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
import re
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

# --- optional per-run mailbox (ported from the task_groups Orchestrator) ---
# run_id -> {"group_id": task_groups row id, "index": {node_id: sender_index}}
_MAILBOXES: dict[str, dict[str, Any]] = {}


def enable_mailbox(run_id: str, group_id: str, node_ids: list[str]) -> None:
    """Give this run's sub-agents mailbox.send / mailbox.read tools."""
    _MAILBOXES[run_id] = {
        "group_id": group_id,
        "index": {nid: i for i, nid in enumerate(node_ids)},
    }


def disable_mailbox(run_id: str) -> None:
    _MAILBOXES.pop(run_id, None)


async def _mailbox_source(ctx: Any) -> list[tuple[Any, Any]]:
    """ToolPlane source: mailbox tools exist only inside a mailbox-enabled run."""
    from app.kernel.types import ToolSpec

    box = _MAILBOXES.get(getattr(ctx, "run_id", ""))
    if not box:
        return []
    group_id = box["group_id"]
    index: dict[str, int] = box["index"]
    peers = ", ".join(index) or "none"

    send_spec = ToolSpec(
        name="mailbox.send",
        description=(
            "Send a message to another sub-agent in this workflow (or broadcast "
            f"when 'to' is omitted). Peers: {peers}."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Peer node id (omit to broadcast)."},
                "content": {"type": "string"},
            },
            "required": ["content"],
        },
        source="builtin", source_id="mailbox.send", danger_level="safe",
    )
    read_spec = ToolSpec(
        name="mailbox.read",
        description="Read messages sent to you (and broadcasts) in this workflow.",
        input_schema={"type": "object", "properties": {}},
        source="builtin", source_id="mailbox.read", danger_level="safe",
    )

    async def send(args: dict[str, Any], c: Any) -> Any:
        from app.services.messaging import messaging_service

        sender = index.get(getattr(c, "agent_label", ""), 0)
        to = args.get("to")
        receiver = index.get(str(to)) if to else None
        row = messaging_service.send(
            group_id=group_id, sender_index=sender, receiver_index=receiver,
            content=str(args.get("content", "")),
            metadata={"node": getattr(c, "agent_label", ""), "to": to},
        )
        return {"sent": True, "id": row.get("id", "")}

    async def read(args: dict[str, Any], c: Any) -> Any:
        from app.services.messaging import messaging_service

        me = index.get(getattr(c, "agent_label", ""), 0)
        rows = messaging_service.get_messages(group_id, receiver_index=me)
        by_index = {i: nid for nid, i in index.items()}
        return {"messages": [
            {"from": by_index.get(int(r.get("sender_index") or 0), "?"),
             "content": r.get("content", "")}
            for r in rows
        ]}

    return [(send_spec, send), (read_spec, read)]


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
    """Execute one sub-agent (or a verify stage) as a blueprint node."""
    if config.get("stage_kind") == "verify":
        return await _execute_verify(config, inputs)
    return await _execute_worker(config, inputs)


def _make_recorder(
    config: dict, user_id: str, run_id: str, node_id: str, user_prompt: str, model: Any
) -> Any:
    """A time-travel recorder for this sub-agent's transcript (best-effort).

    Each sub-agent gets its own ``runs`` row (id ``<run>:<node>``) so replay
    and fork work at workflow scale; failure to record never blocks the run.
    """
    if not run_id or not node_id or not user_id:
        return None
    try:
        from app.db import get_db
        from app.services.timetravel.recorder import RunRecorder

        sub_run_id = f"{run_id}:{node_id}"
        get_db().table("runs").insert({
            "id": sub_run_id,
            "agent_id": config.get("agent_id") or None,
            "user_id": user_id,
            "input_text": user_prompt[:2000],
            "status": "running",
        }).execute()
        recorder = RunRecorder(sub_run_id)
        recorder.run_start(
            agent_id=config.get("agent_id") or None,
            user_input=user_prompt[:2000],
            model=model,
        )
        return recorder
    except Exception:  # noqa: BLE001 - recording must never break a run
        logger.debug("subagent recorder unavailable for %s:%s", run_id, node_id,
                     exc_info=True)
        return None


def _finish_recorder(recorder: Any, status: str, output: str, total_tokens: int) -> None:
    if recorder is None:
        return
    try:
        from app.db import get_db

        recorder.run_end(status=status, output=output[:2000], total_tokens=total_tokens)
        get_db().table("runs").update({
            "status": status, "output": output[:2000], "tokens_used": total_tokens,
        }).eq("id", recorder.run_id).execute()
    except Exception:  # noqa: BLE001
        logger.debug("subagent recorder finish failed", exc_info=True)


async def _execute_worker(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Run one scoped sub-agent through the kernel loop."""
    from app.providers.registry import create_user_registry, provider_registry

    spec: dict[str, Any] = config.get("spec") or {}
    user_id = inputs.get("_user_id", "")
    run_id = inputs.get("_run_id", "")
    node_id = inputs.get("_node_id", "")

    # Budget exhaustion halts the scheduling of new agents: each sub-agent
    # re-checks the user's daily budget before spending anything.
    if user_id:
        try:
            from app.services.budgets import check_user_budget

            budget_status = check_user_budget(user_id)
        except Exception:  # noqa: BLE001 - budget check is best-effort
            budget_status = None
        if budget_status is not None and not budget_status.within_budget:
            raise RuntimeError(
                f"daily budget of ${budget_status.limit_usd:.2f} reached "
                f"(${budget_status.spent_usd:.2f} spent) — sub-agent not started"
            )

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
        agent_label=node_id,
    )

    all_specs = await tool_plane.list_tools(user_id, ctx)
    allow = spec.get("tools", "inherit")
    if isinstance(allow, list):
        allowed_names = set(allow)
        tools = [s for s in all_specs if s.name in allowed_names]
        # The mailbox (when enabled for this run) is coordination plumbing,
        # not a capability — it rides along regardless of the allowlist.
        tools += [s for s in all_specs
                  if s.name.startswith("mailbox.") and s.name not in allowed_names]
    else:
        tools = list(all_specs)
    tools = [s for s in tools if s.name not in _FORBIDDEN_SUBAGENT_TOOLS]

    budget_spec = spec.get("budget") or {}
    budget = Budget(
        max_tokens=budget_spec.get("max_tokens"),
        max_seconds=budget_spec.get("max_seconds"),
    )

    user_prompt = _user_prompt(spec, inputs)
    messages = [
        KMessage(role="system", blocks=[TextBlock(_system_prompt(spec, config))]),
        KMessage(role="user", blocks=[TextBlock(user_prompt)]),
    ]

    registry = await create_user_registry(user_id) or provider_registry
    recorder = _make_recorder(config, user_id, run_id, node_id, user_prompt, model)

    input_tokens = 0
    output_tokens = 0
    final_text = ""
    status = "completed"
    sem = _run_semaphore(run_id or "adhoc", int(config.get("max_concurrent", 16) or 16))
    async with sem:
        try:
            async for ev in run_agent_turn(
                messages, tools or None, model,
                registry=registry, plane=tool_plane, ctx=ctx, budget=budget,
                recorder=recorder,
                max_iterations=_MAX_SUBAGENT_ITERATIONS,
            ):
                if isinstance(ev, TurnDone):
                    input_tokens += ev.turn.usage.input_tokens
                    output_tokens += ev.turn.usage.output_tokens
                    if ev.turn.stop_reason != "tool_use":
                        final_text = ev.turn.text
        except BaseException:
            status = "failed"
            raise
        finally:
            _finish_recorder(recorder, status, final_text, input_tokens + output_tokens)

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
        # producers apart after the engine's fan-in merge. Carries the spec and
        # the exact prompt so a failed producer can be retried (Phase 9.4).
        result[f"result_{node_id}"] = {
            "node_id": node_id,
            "role": result["role"],
            "text": final_text,
            "success_criteria": spec.get("success_criteria", ""),
            "spec": dict(spec),
            "user_prompt": _user_prompt(spec, inputs),
        }
    return result


# --- the verify stage (Phase 9.4) ---


def _parse_verdicts(raw_text: str) -> list[dict[str, Any]] | None:
    """Parse the reviewer's reply into [{node_id, verdict, findings}, ...]."""
    text = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
    if start == -1:
        return None
    end = max(text.rfind("}"), text.rfind("]"))
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return None
    out = []
    for item in items:
        if not isinstance(item, dict) or not item.get("node_id"):
            continue
        verdict = str(item.get("verdict", "")).lower()
        out.append({
            "node_id": str(item["node_id"]),
            "verdict": verdict if verdict in ("pass", "fail") else "unknown",
            "findings": str(item.get("findings", "")),
        })
    return out or None


def _review_prompt(goal: str, producers: dict[str, dict[str, Any]]) -> str:
    items = [
        {
            "node_id": nid,
            "role": p.get("role", "worker"),
            "success_criteria": p.get("success_criteria", ""),
            "output": str(p.get("text", "")),
        }
        for nid, p in sorted(producers.items())
    ]
    return (
        (f"Workflow goal: {goal}\n\n" if goal else "")
        + "Judge each item's output against its success_criteria. Answer with "
        'ONE JSON object: {"items": [{"node_id": "...", "verdict": "pass"|"fail", '
        '"findings": "what is wrong or missing (empty when pass)"}]} — one entry '
        "per item, no prose.\n\nItems:\n"
        + json.dumps(items, indent=2, default=str)
    )


async def _run_reviewer(
    config: dict, inputs: dict[str, Any], producers: dict[str, dict[str, Any]], label: str
) -> tuple[list[dict[str, Any]] | None, dict[str, Any]]:
    """One reviewer pass over ``producers``; returns (verdicts, raw result)."""
    reviewer_inputs = {
        "_user_id": inputs.get("_user_id", ""),
        "_run_id": inputs.get("_run_id", ""),
        "_node_id": label,
        "text": _review_prompt(str(config.get("workflow_title", "")), producers),
    }
    result = await _execute_worker(config, reviewer_inputs)
    return _parse_verdicts(str(result.get("text", ""))), result


async def _execute_verify(config: dict, inputs: dict[str, Any]) -> dict[str, Any]:
    """Judge every producer's output; failures get one bounded retry.

    Generalizes ``cu_verifier`` to the whole platform: the reviewer sub-agent
    never wrote the answers it judges, failures are re-run once with the
    findings attached, and the retried output is re-judged.
    """
    node_id = inputs.get("_node_id", "")
    producers = {
        k[len("result_"):]: v
        for k, v in inputs.items()
        if k.startswith("result_") and isinstance(v, dict)
    }
    if not producers:
        # Nothing structured to judge — run as a plain sub-agent.
        return await _execute_worker(config, inputs)

    input_tokens = 0
    output_tokens = 0

    verdicts, review_result = await _run_reviewer(config, inputs, producers, f"{node_id}-review")
    input_tokens += int(review_result.get("input_tokens", 0))
    output_tokens += int(review_result.get("output_tokens", 0))

    items: dict[str, dict[str, Any]] = {
        nid: {
            "node_id": nid,
            "verdict": "unknown",
            "findings": "",
            "text": str(p.get("text", "")),
            "retried": False,
        }
        for nid, p in producers.items()
    }
    for v in verdicts or []:
        if v["node_id"] in items:
            items[v["node_id"]].update(verdict=v["verdict"], findings=v["findings"])

    # One bounded retry per failed producer, findings attached, then re-judge.
    for nid, item in items.items():
        if item["verdict"] != "fail":
            continue
        producer = producers[nid]
        pspec = dict(producer.get("spec") or {})
        if not pspec.get("prompt"):
            continue  # nothing to re-run (no spec carried)
        pspec["prompt"] = (
            f"{pspec['prompt']}\n\nA reviewer failed your previous attempt.\n"
            f"Findings: {item['findings']}\n"
            f"Your previous output:\n{item['text']}\n\n"
            "Address every finding and produce a corrected result."
        )
        retry_config = {**config, "spec": pspec, "stage_kind": "single"}
        retry_inputs = {
            "_user_id": inputs.get("_user_id", ""),
            "_run_id": inputs.get("_run_id", ""),
            "_node_id": f"{nid}-retry",
            "text": str(producer.get("user_prompt", "")),
        }
        try:
            retry = await _execute_worker(retry_config, retry_inputs)
        except Exception:  # noqa: BLE001 - a failed retry keeps the fail verdict
            logger.warning("verify retry for %s failed", nid, exc_info=True)
            continue
        input_tokens += int(retry.get("input_tokens", 0))
        output_tokens += int(retry.get("output_tokens", 0))
        item["retried"] = True
        item["text"] = str(retry.get("text", ""))

        re_verdicts, re_result = await _run_reviewer(
            config, inputs,
            {nid: {**producer, "text": item["text"]}},
            f"{node_id}-review-{nid}-retry",
        )
        input_tokens += int(re_result.get("input_tokens", 0))
        output_tokens += int(re_result.get("output_tokens", 0))
        for v in re_verdicts or []:
            if v["node_id"] == nid:
                item.update(verdict=v["verdict"], findings=v["findings"])

    ordered = [items[nid] for nid in sorted(items)]
    passed = sum(1 for i in ordered if i["verdict"] == "pass")
    failed = sum(1 for i in ordered if i["verdict"] == "fail")
    summary_lines = [f"Verification: {passed} pass, {failed} fail, "
                     f"{len(ordered) - passed - failed} unknown."]
    for i in ordered:
        line = f"- {i['node_id']}: {i['verdict']}"
        if i["retried"]:
            line += " (after retry)"
        if i["findings"]:
            line += f" — {i['findings']}"
        summary_lines.append(line)

    result: dict[str, Any] = {
        "text": "\n".join(summary_lines),
        "role": (config.get("spec") or {}).get("role", "reviewer"),
        "verdicts": {i["node_id"]: i["verdict"] for i in ordered},
        "items": ordered,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "agent_id": config.get("agent_id", ""),
    }
    if node_id:
        result[f"result_{node_id}"] = {
            "node_id": node_id,
            "role": result["role"],
            "text": result["text"],
            "success_criteria": (config.get("spec") or {}).get("success_criteria", ""),
        }
    return result


SUBAGENT_EXECUTORS = {
    "subagent_run": execute_subagent_run,
}

# The mailbox tools appear on the plane only inside mailbox-enabled runs.
tool_plane.register_source(_mailbox_source)
