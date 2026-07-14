"""Session (durable chat) API routes (harness-plan.md Phase 6).

Gated by ``FORGE_SESSIONS`` — endpoints 404 until the flag is on.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config.flags import sessions_enabled
from app.routers.auth import get_current_user
from app.services import sessions as svc

router = APIRouter(tags=["sessions"])


def _require_flag() -> None:
    if not sessions_enabled():
        raise HTTPException(status_code=404, detail="Sessions are not enabled (FORGE_SESSIONS)")


class SessionCreate(BaseModel):
    title: str = ""
    model: str = ""
    workspace_root: str = ""
    system_prompt: str = ""
    policy: dict[str, Any] = Field(default_factory=dict)
    token_budget: int = 0


class SessionUpdate(BaseModel):
    title: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    status: str | None = None


class MessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000)
    model: str | None = None  # optional mid-session model switch


@router.post("/sessions")
async def create_session(body: SessionCreate, user: Any = Depends(get_current_user)):  # noqa: B008
    _require_flag()
    return svc.create_session(
        user.id, title=body.title, model=body.model, workspace_root=body.workspace_root,
        system_prompt=body.system_prompt, policy=body.policy, token_budget=body.token_budget,
    )


@router.get("/sessions")
async def list_sessions(user: Any = Depends(get_current_user)):  # noqa: B008
    _require_flag()
    return svc.list_sessions(user.id)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user: Any = Depends(get_current_user)):  # noqa: B008
    _require_flag()
    session = svc.get_session(session_id, user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session, "events": svc.get_events(session_id)}


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: str, body: SessionUpdate, user: Any = Depends(get_current_user)  # noqa: B008
):
    _require_flag()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    session = svc.update_session(session_id, user.id, updates)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/sessions/{session_id}/fork")
async def fork_session(session_id: str, user: Any = Depends(get_current_user)):  # noqa: B008
    _require_flag()
    child = svc.fork_session(session_id, user.id)
    if child is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return child


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, user: Any = Depends(get_current_user)):  # noqa: B008
    _require_flag()
    if svc.get_session(session_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    from app.db import get_db

    get_db().table("sessions").delete().eq("id", session_id).execute()


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: str, body: MessageRequest, user: Any = Depends(get_current_user)  # noqa: B008
):
    _require_flag()
    if svc.get_session(session_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_stream():
        async for event in svc.run_turn(
            session_id, user.id, body.text, model_override=body.model
        ):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
