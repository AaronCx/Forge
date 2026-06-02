"""Onboarding finish — clone templates, create custom agents, tailor + seed."""

import logging
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.db import get_db
from app.routers.auth import get_current_user
from app.services.tailoring import MAX_INSTRUCTIONS, prepend_about

logger = logging.getLogger(__name__)
router = APIRouter(tags=["onboarding"])

_EXPAND_SYSTEM = (
    "You write concise, effective system prompts for AI agents. Given a "
    "plain-language description of what an agent should do, output ONLY the "
    "system prompt text — no preamble, no markdown headers. Keep it focused "
    "and under 200 words."
)


class CustomAgentSpec(BaseModel):
    name: str | None = None
    description: str


class OnboardingFinishRequest(BaseModel):
    use_case: str | None = None
    custom_instructions: str | None = None
    template_ids: list[str] = []
    custom_agents: list[CustomAgentSpec] = []


def _derive_name(description: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", description)[:4]
    return " ".join(w.capitalize() for w in words) or "Custom Agent"


async def _expand_or_verbatim(user_id: str, description: str) -> str:
    """Expand a plain-language description into a system prompt via the user's
    connected model, falling back to the raw text when no provider is set."""
    try:
        from app.providers.registry import create_user_registry

        registry = await create_user_registry(user_id)
        if not registry.provider_names:
            return description
        response = await registry.complete(
            messages=[
                {"role": "system", "content": _EXPAND_SYSTEM},
                {"role": "user", "content": description},
            ],
            temperature=0.3,
            max_tokens=600,
        )
        return (response.content or "").strip() or description
    except Exception:
        logger.info("Prompt expansion unavailable; using verbatim description", exc_info=True)
        return description


def _insert_agent(user_id: str, *, name: str, description: str, system_prompt: str,
                  tools: list, workflow_steps: list, model: str | None) -> dict | None:
    result = get_db().table("agents").insert({
        "user_id": user_id,
        "name": name,
        "description": description,
        "system_prompt": system_prompt,
        "tools": tools,
        "workflow_steps": workflow_steps,
        "model": model,
        "is_template": False,
    }).execute()
    return result.data[0] if result.data else None


@router.post("/onboarding/finish")
async def finish_onboarding(req: OnboardingFinishRequest, user=Depends(get_current_user)):  # noqa: B008
    """Seed the user's chosen agents, tailored with their custom instructions."""
    user_id = user.id
    instructions = (req.custom_instructions or "").strip()[:MAX_INSTRUCTIONS]
    created: list[dict] = []

    # 1. Clone selected templates, embedding the user's context.
    for template_id in req.template_ids:
        tpl = get_db().table("agents").select("*").eq("id", template_id).single().execute()
        if not tpl.data or not tpl.data.get("is_template"):
            continue
        t = tpl.data
        agent = _insert_agent(
            user_id,
            name=t.get("name", "Agent"),
            description=t.get("description", "") or "",
            system_prompt=prepend_about(t.get("system_prompt", ""), instructions),
            tools=t.get("tools", []) or [],
            workflow_steps=t.get("workflow_steps", []) or [],
            model=t.get("model"),
        )
        if agent:
            created.append(agent)

    # 2. Create custom agents from plain-language descriptions.
    for spec in req.custom_agents:
        desc = (spec.description or "").strip()
        if not desc:
            continue
        system_prompt = await _expand_or_verbatim(user_id, desc)
        agent = _insert_agent(
            user_id,
            name=spec.name or _derive_name(desc),
            description=desc[:200],
            system_prompt=prepend_about(system_prompt, instructions),
            tools=[],
            workflow_steps=[],
            model=None,
        )
        if agent:
            created.append(agent)

    # 3. Persist use_case + custom_instructions and mark onboarded.
    from app.routers.preferences import _get_or_create

    _get_or_create(user_id)
    now = datetime.now(UTC).isoformat()
    patch: dict = {"onboarded_at": now, "updated_at": now}
    if req.use_case:
        patch["use_case"] = req.use_case
    if instructions:
        patch["custom_instructions"] = instructions
    get_db().table("user_preferences").update(patch).eq("user_id", user_id).execute()

    return {
        "ok": True,
        "created_agents": len(created),
        "agents": [{"id": a.get("id"), "name": a.get("name")} for a in created],
    }
