"""Message API routes for inter-agent communication."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.routers.auth import get_current_user
from app.database import supabase
from app.services.messaging import messaging_service

router = APIRouter(tags=["messages"])


class SendMessageRequest(BaseModel):
    group_id: str
    sender_index: int
    receiver_index: int | None = None
    message_type: str = "info"
    content: str
    metadata: dict | None = None


@router.post("/messages")
async def send_message(body: SendMessageRequest, user=Depends(get_current_user)):
    """Send a message between agents."""
    # Verify group belongs to user
    group = (
        supabase.table("task_groups")
        .select("id")
        .eq("id", body.group_id)
        .eq("user_id", user.id)
        .single()
        .execute()
    )
    if not group.data:
        raise HTTPException(status_code=404, detail="Group not found")

    msg = messaging_service.send(
        group_id=body.group_id,
        sender_index=body.sender_index,
        receiver_index=body.receiver_index,
        message_type=body.message_type,
        content=body.content,
        metadata=body.metadata,
    )
    return msg


@router.get("/messages/{group_id}")
async def get_messages(
    group_id: str,
    receiver_index: int | None = Query(None),
    message_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
):
    """Get messages for a task group."""
    # Verify group belongs to user
    group = (
        supabase.table("task_groups")
        .select("id")
        .eq("id", group_id)
        .eq("user_id", user.id)
        .single()
        .execute()
    )
    if not group.data:
        raise HTTPException(status_code=404, detail="Group not found")

    return messaging_service.get_messages(
        group_id,
        receiver_index=receiver_index,
        message_type=message_type,
        limit=limit,
    )


@router.get("/messages/{group_id}/conversation")
async def get_conversation(
    group_id: str,
    agent_a: int = Query(...),
    agent_b: int = Query(...),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
):
    """Get messages exchanged between two specific agents."""
    group = (
        supabase.table("task_groups")
        .select("id")
        .eq("id", group_id)
        .eq("user_id", user.id)
        .single()
        .execute()
    )
    if not group.data:
        raise HTTPException(status_code=404, detail="Group not found")

    return messaging_service.get_conversation(group_id, agent_a, agent_b, limit)
