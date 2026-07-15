"""Session (durable chat) API routes (harness-plan.md Phase 6).

Gated by ``FORGE_SESSIONS`` — endpoints 404 until the flag is on.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config.flags import sessions_enabled
from app.routers.auth import get_current_user
from app.services import sessions as svc
from app.services.rate_limiter import limiter

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
    effort: Literal["standard", "high", "ultra"] = "standard"


class SessionUpdate(BaseModel):
    title: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    status: str | None = None
    effort: Literal["standard", "high", "ultra"] | None = None


class MessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000)
    model: str | None = None  # optional mid-session model switch


@router.post("/sessions")
@limiter.limit("60/hour")
async def create_session(
    request: Request, body: SessionCreate, user: Any = Depends(get_current_user)  # noqa: B008
):
    _require_flag()
    return svc.create_session(
        user.id, title=body.title, model=body.model, workspace_root=body.workspace_root,
        system_prompt=body.system_prompt, policy=body.policy, token_budget=body.token_budget,
        effort=body.effort,
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
@limiter.limit("120/hour")
async def post_message(
    request: Request, session_id: str, body: MessageRequest,
    user: Any = Depends(get_current_user),  # noqa: B008
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


# --- dynamic orchestration: consent + execution (Phase 9.5) ---


class WorkflowRunRequest(BaseModel):
    """Run a proposed plan by seq, or an (edited) spec directly."""

    plan_seq: int | None = None
    spec: dict[str, Any] | None = None
    confirm: bool = False


class WorkflowSaveRequest(BaseModel):
    plan_seq: int | None = None
    spec: dict[str, Any] | None = None
    name: str = ""


def _resolve_plan(
    session_id: str, plan_seq: int | None, spec: dict[str, Any] | None
) -> tuple[dict[str, Any], str]:
    """Resolve (spec_dict, goal) from a stored plan or an inline spec."""
    from app.services.orchestration.runner import get_plan

    if spec is not None:
        return spec, str(spec.get("goal", "") or "")
    if plan_seq is None:
        raise HTTPException(status_code=422, detail="Provide plan_seq or spec")
    plan = get_plan(session_id, plan_seq)
    if plan is None or not isinstance(plan.get("spec"), dict):
        raise HTTPException(status_code=404, detail="Proposed plan not found")
    return plan["spec"], str(plan.get("goal", ""))


@router.post("/sessions/{session_id}/workflow/run")
@limiter.limit("30/hour")
async def run_workflow(
    request: Request, session_id: str, body: WorkflowRunRequest,
    user: Any = Depends(get_current_user),  # noqa: B008
):
    """Execute a workflow the user consented to (SSE progress stream)."""
    from app.kernel.serialize import workflow_spec_from_dict
    from app.services.orchestration import runner

    _require_flag()
    session = svc.get_session(session_id, user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    spec_dict, goal = _resolve_plan(session_id, body.plan_seq, body.spec)
    agent_count = workflow_spec_from_dict(spec_dict).agent_count
    if agent_count > runner.confirm_threshold() and not body.confirm:
        raise HTTPException(
            status_code=400,
            detail=(
                f"This workflow spawns {agent_count} agents (threshold "
                f"{runner.confirm_threshold()}); re-send with confirm=true."
            ),
        )

    async def event_stream():
        async for event in runner.run_workflow(
            session, spec_dict, goal=goal, plan_seq=body.plan_seq
        ):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/sessions/{session_id}/workflow/save")
@limiter.limit("60/hour")
async def save_workflow(
    request: Request, session_id: str, body: WorkflowSaveRequest,
    user: Any = Depends(get_current_user),  # noqa: B008
):
    """Persist a plan's compiled blueprint to the library (rerunnable/forkable)."""
    from app.services.orchestration import runner

    _require_flag()
    session = svc.get_session(session_id, user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    spec_dict, _goal = _resolve_plan(session_id, body.plan_seq, body.spec)
    try:
        return runner.save_workflow(session, spec_dict, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
