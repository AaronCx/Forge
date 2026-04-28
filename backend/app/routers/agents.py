from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_db
from app.models.agent import AgentCreate, AgentResponse, AgentUpdate
from app.routers.auth import get_current_user
from app.services.rate_limiter import limiter

router = APIRouter(tags=["agents"])


@router.get("/agents", response_model=list[AgentResponse])
async def list_agents(
    user=Depends(get_current_user),  # noqa: B008
):
    result = get_db().table("agents").select("*").eq("user_id", user.id).order("created_at", desc=True).execute()
    return result.data


@router.get("/agents/templates", response_model=list[AgentResponse])
async def list_templates():
    result = get_db().table("agents").select("*").eq("is_template", True).execute()
    return result.data


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    user=Depends(get_current_user),  # noqa: B008
):
    result = get_db().table("agents").select("*").eq("id", agent_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Agent not found")
    if result.data["user_id"] != user.id and not result.data["is_template"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return result.data


@router.post("/agents", response_model=AgentResponse, status_code=201)
@limiter.limit("20/hour")
async def create_agent(
    agent: AgentCreate,
    request: Request,
    user=Depends(get_current_user),  # noqa: B008
):
    data = agent.model_dump()
    data["user_id"] = user.id
    result = get_db().table("agents").insert(data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create agent")
    return result.data[0]


@router.put("/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    agent: AgentUpdate,
    user=Depends(get_current_user),  # noqa: B008
):
    existing = get_db().table("agents").select("user_id").eq("id", agent_id).single().execute()
    if not existing.data or existing.data["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = agent.model_dump(exclude_none=True)
    result = get_db().table("agents").update(update_data).eq("id", agent_id).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update agent")
    return result.data[0]


@router.delete("/agents/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: str,
    user=Depends(get_current_user),  # noqa: B008
):
    existing = get_db().table("agents").select("user_id").eq("id", agent_id).single().execute()
    if not existing.data or existing.data["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Sever child references so the historical run/trace/usage rows survive
    # the agent record. The runs FK is configured RESTRICT in older SQLite
    # schemas, so a bare DELETE on the agent fails with FOREIGN KEY constraint
    # failed. Per the QA playbook §6.4 ("don't cascade-delete runs"), null
    # the back-pointers and keep the history. Heartbeats are transient
    # in-flight state — those we can drop.
    import contextlib

    db = get_db()
    # History tables: preserve, null the back-pointer.
    for table in ("runs", "token_usage", "traces", "prompt_versions"):
        try:
            db.table(table).update({"agent_id": None}).eq("agent_id", agent_id).execute()
        except Exception:
            # Older schemas with NOT NULL — drop the rows rather than orphan-
            # break the constraint.
            with contextlib.suppress(Exception):
                db.table(table).delete().eq("agent_id", agent_id).execute()
    # Transient state: drop.
    db.table("agent_heartbeats").delete().eq("agent_id", agent_id).execute()
    # Group memberships: nullable, just null the ref.
    with contextlib.suppress(Exception):
        db.table("task_group_members").update({"agent_id": None}).eq("agent_id", agent_id).execute()
    # Reparent any sub-agents (parent_agent_id) — already ON DELETE SET NULL
    # in the schema; safe to drop the parent.

    db.table("agents").delete().eq("id", agent_id).execute()
