"""Durable conversation sessions (harness-plan.md Phase 6).

A session is a persistent, resumable thread: its ``session_events`` are an
append-only log of kernel messages. ``run_turn`` drives the native kernel loop
over the reconstructed history, streams events, and appends the new turns.
Compaction summarizes the oldest span into a pinned system note while keeping
the originals in the log (reversible).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from app.db import get_db
from app.kernel.loop import Budget, ToolExecuted, run_agent_turn
from app.kernel.serialize import message_from_dict, message_to_dict
from app.kernel.toolplane import ExecContext, tool_plane
from app.kernel.types import (
    KMessage,
    TextBlock,
    TextDelta,
    ThinkingDelta,
    ToolResultBlock,
    ToolUseStart,
    TurnDone,
    UsageEvent,
)

logger = logging.getLogger(__name__)

_WORKSPACE_INJECT_CHARS = 8000  # ~2k tokens cap for AGENTS.md/CLAUDE.md
_KEEP_LAST_MESSAGES = 8  # verbatim tail preserved by compaction
_COMPACT_RATIO = 0.8


def _now() -> str:
    return datetime.now(UTC).isoformat()


# --- CRUD ---


def create_session(
    user_id: str,
    *,
    title: str = "",
    model: str = "",
    workspace_root: str = "",
    system_prompt: str = "",
    policy: dict[str, Any] | None = None,
    token_budget: int = 0,
) -> dict[str, Any]:
    row = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "title": title or "New session",
        "model": model,
        "workspace_root": workspace_root,
        "system_prompt": system_prompt,
        "policy_json": policy or {},
        "token_budget": token_budget,
        "status": "active",
    }
    result = get_db().table("sessions").insert(row).execute()
    return result.data[0] if result.data else row


def get_session(session_id: str, user_id: str) -> dict[str, Any] | None:
    result = get_db().table("sessions").select("*").eq("id", session_id).execute()
    rows = result.data if isinstance(result.data, list) else []
    session: dict[str, Any] | None = rows[0] if rows else None
    if not session or session.get("user_id") != user_id:
        return None
    return session


def list_sessions(user_id: str) -> list[dict[str, Any]]:
    result = (
        get_db().table("sessions").select("*").eq("user_id", user_id)
        .order("updated_at", desc=True).execute()
    )
    return result.data if isinstance(result.data, list) else []


def update_session(session_id: str, user_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    if get_session(session_id, user_id) is None:
        return None
    allowed = {"title", "model", "workspace_root", "system_prompt", "policy_json",
               "token_budget", "status"}
    patch = {k: v for k, v in updates.items() if k in allowed}
    patch["updated_at"] = _now()
    get_db().table("sessions").update(patch).eq("id", session_id).execute()
    return get_session(session_id, user_id)


# --- event log ---


def _next_seq(session_id: str) -> int:
    result = get_db().table("session_events").select("seq").eq("session_id", session_id).execute()
    rows = result.data if isinstance(result.data, list) else []
    return (max((r.get("seq", 0) for r in rows), default=-1) + 1) if rows else 0


def append_event(session_id: str, kind: str, payload: dict[str, Any]) -> int:
    seq = _next_seq(session_id)
    get_db().table("session_events").insert({
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "seq": seq,
        "kind": kind,
        "payload_json": payload,
    }).execute()
    return seq


def get_events(session_id: str) -> list[dict[str, Any]]:
    result = (
        get_db().table("session_events").select("*").eq("session_id", session_id)
        .order("seq").execute()
    )
    rows = result.data if isinstance(result.data, list) else []
    return sorted(rows, key=lambda r: r.get("seq", 0))


# --- workspace convention: AGENTS.md / CLAUDE.md ---


def _workspace_instructions(workspace_root: str) -> str:
    if not workspace_root:
        return ""
    from pathlib import Path

    for name in ("AGENTS.md", "CLAUDE.md"):
        path = Path(workspace_root) / name
        try:
            if path.is_file():
                text = path.read_text(errors="replace")[:_WORKSPACE_INJECT_CHARS]
                return f"--- {name} (workspace instructions) ---\n{text}"
        except OSError:
            continue
    return ""


# --- message reconstruction ---


def build_messages(session: dict[str, Any]) -> list[KMessage]:
    """Reconstruct the live kernel message list from the event log."""
    events = get_events(session["id"])

    # A compaction event pins a summary and marks history up to a seq as replaced.
    summaries: list[str] = []
    replaced_up_to = -1
    for ev in events:
        if ev.get("kind") == "compaction":
            payload = ev.get("payload_json") or {}
            summaries.append(str(payload.get("summary", "")))
            replaced_up_to = max(replaced_up_to, int(payload.get("replaced_up_to_seq", -1)))

    system_parts = [session.get("system_prompt", "")]
    ws = _workspace_instructions(session.get("workspace_root", ""))
    if ws:
        system_parts.append(ws)
    for summary in summaries:
        if summary:
            system_parts.append(f"--- Summary of earlier conversation ---\n{summary}")
    system_text = "\n\n".join(p for p in system_parts if p)

    messages: list[KMessage] = []
    if system_text:
        messages.append(KMessage(role="system", blocks=[TextBlock(system_text)]))
    for ev in events:
        if ev.get("kind") != "message" or ev.get("seq", 0) <= replaced_up_to:
            continue
        messages.append(message_from_dict(ev.get("payload_json") or {}))
    return messages


# --- compaction ---


def _estimate_tokens(messages: list[KMessage]) -> int:
    total = 0
    for m in messages:
        for b in m.blocks:
            total += len(getattr(b, "text", "") or str(getattr(b, "output", ""))) // 4
    return total


async def compact_session(
    session_id: str,
    user_id: str,
    *,
    keep_last: int = _KEEP_LAST_MESSAGES,
    force: bool = False,
) -> bool:
    """Summarize the oldest span into a pinned note if the context is too large.

    Returns True if a compaction happened. Originals stay in ``session_events``
    (a compaction event only marks them replaced), so it is reversible.
    """
    from app.kernel.models import get_model_card
    from app.providers.registry import create_user_registry, provider_registry

    session = get_session(session_id, user_id)
    if session is None:
        return False

    messages = build_messages(session)
    message_events = [e for e in get_events(session_id) if e.get("kind") == "message"]
    if len(message_events) <= keep_last:
        return False

    card = get_model_card(session.get("model", ""))
    threshold = int(card.context_window * _COMPACT_RATIO) if card else 0
    if not force and (threshold == 0 or _estimate_tokens(messages) < threshold):
        return False

    # Summarize everything except the last `keep_last` message events.
    to_summarize = message_events[:-keep_last]
    replaced_up_to = max(e.get("seq", 0) for e in to_summarize)
    transcript = "\n\n".join(
        _message_text(message_from_dict(e.get("payload_json") or {})) for e in to_summarize
    )

    registry = await create_user_registry(user_id) or provider_registry
    summary_prompt = [
        KMessage(role="system", blocks=[TextBlock(
            "Summarize the following conversation faithfully and concisely, "
            "preserving decisions, facts, and open threads. Output only the summary."
        )]),
        KMessage(role="user", blocks=[TextBlock(transcript[:20000])]),
    ]
    try:
        turn = await registry.turn(summary_prompt, session.get("model") or None)
        summary = turn.text
    except Exception as exc:  # noqa: BLE001 - compaction must not break a session
        logger.warning("compaction summary failed for %s: %s", session_id, exc)
        return False

    append_event(session_id, "compaction", {
        "summary": summary, "replaced_up_to_seq": replaced_up_to,
    })
    return True


def _message_text(m: KMessage) -> str:
    parts = []
    for b in m.blocks:
        if isinstance(b, TextBlock):
            parts.append(f"{m.role}: {b.text}")
        elif isinstance(b, ToolResultBlock):
            parts.append(f"tool_result: {str(b.output)[:500]}")
    return "\n".join(parts)


# --- the turn driver (SSE) ---


async def run_turn(
    session_id: str,
    user_id: str,
    user_text: str,
    *,
    model_override: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run one chat turn on a session, streaming events and persisting the log."""
    from app.providers.registry import create_user_registry, provider_registry

    session = get_session(session_id, user_id)
    if session is None:
        yield {"type": "error", "data": "Session not found"}
        return

    # Enforce the per-user daily cost budget before spending anything.
    from app.services.budgets import check_user_budget

    budget_status = check_user_budget(user_id)
    if not budget_status.within_budget:
        yield {"type": "error", "data": (
            f"Daily budget of ${budget_status.limit_usd:.2f} reached "
            f"(${budget_status.spent_usd:.2f} spent today)."
        )}
        yield {"type": "done", "session_id": session_id}
        return

    if model_override and model_override != session.get("model"):
        update_session(session_id, user_id, {"model": model_override})
        session["model"] = model_override
    model = session.get("model") or None

    # Persist the user message, then reconstruct the live message list.
    append_event(session_id, "message",
                 message_to_dict(KMessage(role="user", blocks=[TextBlock(user_text)])))
    messages = build_messages(session)
    persist_from = len(messages)

    registry = await create_user_registry(user_id) or provider_registry
    ctx = ExecContext(
        user_id=user_id, session_id=session_id,
        workspace_root=session.get("workspace_root", ""),
        session_overrides=session.get("policy_json") or {},
    )
    specs = await tool_plane.list_tools(user_id, ctx)
    budget = Budget(max_tokens=session.get("token_budget") or None)

    final_turn = None
    async for ev in run_agent_turn(
        messages, specs, model, registry=registry, plane=tool_plane, ctx=ctx, budget=budget,
    ):
        if isinstance(ev, TextDelta):
            yield {"type": "token", "data": ev.text}
        elif isinstance(ev, ThinkingDelta):
            yield {"type": "thinking", "data": ev.text}
        elif isinstance(ev, ToolUseStart):
            yield {"type": "tool_use", "data": {"id": ev.id, "name": ev.name}}
        elif isinstance(ev, UsageEvent):
            yield {"type": "usage", "data": {
                "input_tokens": ev.usage.input_tokens, "output_tokens": ev.usage.output_tokens}}
        elif isinstance(ev, ToolExecuted):
            yield {"type": "tool_result", "data": {
                "tool": ev.tool_use.name, "output": str(ev.result.output)[:2000],
                "is_error": ev.result.is_error}}
        elif isinstance(ev, TurnDone):
            final_turn = ev.turn
            yield {"type": "turn_done", "data": {"stop_reason": ev.turn.stop_reason}}

    # The loop appends assistant tool-turns to `messages` itself; the final
    # (non-tool) answer is only in its TurnDone, so append it before persisting.
    if final_turn is not None and final_turn.stop_reason != "tool_use":
        messages.append(KMessage(role="assistant", blocks=list(final_turn.blocks)))

    # Persist the assistant/tool messages produced this turn.
    for m in messages[persist_from:]:
        append_event(session_id, "message", message_to_dict(m))
    update_session(session_id, user_id, {"updated_at": _now()})

    # Compact if the context has grown too large (reversible; originals kept).
    try:
        await compact_session(session_id, user_id)
    except Exception:
        logger.warning("post-turn compaction failed for %s", session_id, exc_info=True)

    yield {"type": "done", "session_id": session_id}


def fork_session(session_id: str, user_id: str, *, title: str = "") -> dict[str, Any] | None:
    """Fork a session: a new session with a copy of the event log."""
    source = get_session(session_id, user_id)
    if source is None:
        return None
    child = create_session(
        user_id,
        title=title or f"Fork of {source.get('title', 'session')}",
        model=source.get("model", ""),
        workspace_root=source.get("workspace_root", ""),
        system_prompt=source.get("system_prompt", ""),
        policy=source.get("policy_json") or {},
        token_budget=source.get("token_budget", 0),
    )
    for ev in get_events(session_id):
        append_event(child["id"], ev.get("kind", "message"), ev.get("payload_json") or {})
    return child
