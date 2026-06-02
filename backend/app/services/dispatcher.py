"""Dispatcher — turns a free-text message into a routing decision.

``build_catalog`` collects the user's agents + blueprints (names + descriptions
only, to keep the prompt small). ``route`` asks the user's LLM to pick a target
and rewrite the task, returning a structured :class:`Decision`. The routing
call's tokens are tracked via ``token_tracker`` under provider ``dispatcher``.
"""

from __future__ import annotations

import json
import logging
import re

from app.db import get_db
from app.models.dispatch import CatalogEntry, Decision

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a task dispatcher for an AI agent platform. Given a \
user's message and a catalog of the agents and blueprints they own, decide which \
one should handle the task.

Respond with ONLY a JSON object (no prose, no code fences) of the form:
{
  "action": "route" | "clarify" | "none",
  "target_type": "agent" | "blueprint" | null,
  "target_id": "<id from the catalog, or null>",
  "input_text": "<the task, rewritten clearly for the chosen target>",
  "rationale": "<one short line: why this target>",
  "clarifying_question": "<a question, only when action is 'clarify'>"
}

Rules:
- "route": you are confident which catalog entry fits. Set target_type/target_id \
to an entry from the catalog and rewrite the user's task into input_text.
- "clarify": two or more entries fit comparably, or the request is ambiguous. \
Ask one short clarifying_question and leave target_id null.
- "none": nothing in the catalog fits. Leave target_id null.
- target_id MUST be copied verbatim from the catalog. Never invent an id."""


def build_catalog(user_id: str) -> list[CatalogEntry]:
    """Collect the user's agents + blueprints as routable catalog entries."""
    entries: list[CatalogEntry] = []

    try:
        agents = (
            get_db().table("agents")
            .select("id, name, description")
            .eq("user_id", user_id)
            .execute()
        )
        for a in agents.data or []:
            entries.append(
                CatalogEntry(type="agent", id=a["id"], name=a.get("name", ""), description=a.get("description", "") or "")
            )
    except Exception:
        logger.warning("Failed to load agents for catalog", exc_info=True)

    try:
        blueprints = (
            get_db().table("blueprints")
            .select("id, name, description")
            .eq("user_id", user_id)
            .execute()
        )
        for b in blueprints.data or []:
            entries.append(
                CatalogEntry(type="blueprint", id=b["id"], name=b.get("name", ""), description=b.get("description", "") or "")
            )
    except Exception:
        logger.warning("Failed to load blueprints for catalog", exc_info=True)

    return entries


async def build_attachments_summary(attachments: list[dict]) -> str:
    """A short summary of attachments for the routing prompt.

    Lists each attachment's name + kind, and for documents includes the first
    ~500 chars of extracted text so routing can use file content (PR-5).
    """
    if not attachments:
        return ""

    from app.services.extract import extract_text

    lines: list[str] = []
    for att in attachments:
        name = att.get("name") or att.get("url", "")
        kind = att.get("kind", "file")
        if kind == "document":
            try:
                text = await extract_text(att.get("url", ""))
                preview = text[:500].strip().replace("\n", " ")
                lines.append(f"- {name} (document): {preview}")
            except Exception:
                lines.append(f"- {name} (document): <unreadable>")
        else:
            lines.append(f"- {name} ({kind})")
    return "\n".join(lines)


def _format_catalog(catalog: list[CatalogEntry]) -> str:
    lines = []
    for e in catalog:
        desc = e.description.strip().replace("\n", " ")
        if len(desc) > 200:
            desc = desc[:200] + "…"
        lines.append(f"- type={e.type} id={e.id} name={e.name!r} description={desc!r}")
    return "\n".join(lines)


def _build_messages(catalog: list[CatalogEntry], message: str, attachments_summary: str) -> list[dict]:
    user_parts = [f"Catalog:\n{_format_catalog(catalog)}", f"\nUser message:\n{message}"]
    if attachments_summary:
        user_parts.append(f"\nAttachments:\n{attachments_summary}")
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(user_parts)},
    ]


async def _invoke(user_id: str, messages: list[dict]) -> tuple[str, int, int, str]:
    """Call the user's LLM and return (text, input_tokens, output_tokens, model).

    Prefers the shared OpenAI client (``get_user_llm``); falls back to the
    user's provider registry so Ollama-only stacks still route. This is the
    single seam unit tests patch.
    """
    from app.services.llm import get_user_llm

    llm = await get_user_llm(user_id, streaming=False, temperature=0)
    if llm is not None:
        response = await llm.ainvoke([(m["role"], m["content"]) for m in messages])
        text = response.content if isinstance(response.content, str) else str(response.content)
        usage = getattr(response, "usage_metadata", None) or {}
        model = (getattr(response, "response_metadata", {}) or {}).get("model_name") or "gpt-4o-mini"
        return text, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)), model

    from app.providers.registry import create_user_registry

    registry = await create_user_registry(user_id)
    result = await registry.complete(messages=messages, temperature=0)
    return result.content, result.input_tokens, result.output_tokens, result.model


def _track(user_id: str, model: str, input_tokens: int, output_tokens: int) -> None:
    """Record the routing call's tokens under provider 'dispatcher'."""
    try:
        from app.services.token_tracker import token_tracker

        token_tracker.record(
            run_id=None,  # type: ignore[arg-type]
            agent_id=None,  # type: ignore[arg-type]
            user_id=user_id,
            step_number=0,
            model=model or "unknown",
            provider="dispatcher",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    except Exception:
        logger.warning("Failed to track dispatcher routing tokens", exc_info=True)


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of an LLM response (tolerant of fences)."""
    cleaned = text.strip()
    # Strip ```json ... ``` fences if present.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if brace:
            cleaned = brace.group(0)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


def parse_decision(text: str, catalog: list[CatalogEntry]) -> Decision:
    """Parse + validate the LLM response into a Decision.

    Falls back to ``none`` on unparseable output, and downgrades a ``route``
    whose target_id isn't in the catalog to ``clarify`` (the model hallucinated
    an id).
    """
    valid_ids = {e.id: e for e in catalog}
    try:
        data = _extract_json(text)
    except Exception:
        logger.warning("Dispatcher returned unparseable JSON: %r", text[:200])
        return Decision(action="none", rationale="Could not parse a routing decision.")

    action = data.get("action", "none")
    if action == "route":
        target_id = data.get("target_id")
        entry = valid_ids.get(target_id) if target_id else None
        if not entry:
            return Decision(
                action="clarify",
                clarifying_question=data.get("clarifying_question")
                or "I couldn't match that to one of your agents — which one should handle it?",
                rationale="Routing target was not in the catalog.",
            )
        return Decision(
            action="route",
            target_type=entry.type,
            target_id=entry.id,
            input_text=data.get("input_text") or "",
            rationale=data.get("rationale", ""),
        )

    if action == "clarify":
        return Decision(
            action="clarify",
            clarifying_question=data.get("clarifying_question") or "Could you clarify what you'd like done?",
            rationale=data.get("rationale", ""),
        )

    return Decision(action="none", rationale=data.get("rationale", "") or "No matching agent or blueprint.")


async def route(
    user_id: str,
    message: str,
    attachments_summary: str = "",
    *,
    catalog: list[CatalogEntry] | None = None,
) -> Decision:
    """Decide how to route ``message`` for ``user_id``."""
    if catalog is None:
        catalog = build_catalog(user_id)
    if not catalog:
        return Decision(action="none", rationale="You have no agents or blueprints yet.")

    messages = _build_messages(catalog, message, attachments_summary)
    text, input_tokens, output_tokens, model = await _invoke(user_id, messages)
    _track(user_id, model, input_tokens, output_tokens)
    return parse_decision(text, catalog)
