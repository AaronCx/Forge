from fastapi import APIRouter, Depends, HTTPException
from app.routers.auth import get_current_user
from app.models.agent import AgentCreate, AgentUpdate, AgentResponse
from app.database import supabase

router = APIRouter(tags=["agents"])


@router.get("/agents", response_model=list[AgentResponse])
async def list_agents(user=Depends(get_current_user)):
    result = supabase.table("agents").select("*").eq("user_id", user.id).order("created_at", desc=True).execute()
    return result.data


@router.get("/agents/templates", response_model=list[AgentResponse])
async def list_templates():
    result = supabase.table("agents").select("*").eq("is_template", True).execute()
    return result.data


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, user=Depends(get_current_user)):
    result = supabase.table("agents").select("*").eq("id", agent_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Agent not found")
    if result.data["user_id"] != user.id and not result.data["is_template"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return result.data


@router.post("/agents", response_model=AgentResponse, status_code=201)
async def create_agent(agent: AgentCreate, user=Depends(get_current_user)):
    data = agent.model_dump()
    data["user_id"] = user.id
    result = supabase.table("agents").insert(data).execute()
    return result.data[0]


@router.put("/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: str, agent: AgentUpdate, user=Depends(get_current_user)):
    existing = supabase.table("agents").select("user_id").eq("id", agent_id).single().execute()
    if not existing.data or existing.data["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = agent.model_dump(exclude_none=True)
    result = supabase.table("agents").update(update_data).eq("id", agent_id).execute()
    return result.data[0]


@router.delete("/agents/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, user=Depends(get_current_user)):
    existing = supabase.table("agents").select("user_id").eq("id", agent_id).single().execute()
    if not existing.data or existing.data["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")

    supabase.table("agents").delete().eq("id", agent_id).execute()
