"""Saved dynamic workflows (Phase 9.6).

Saved workflows are blueprints carrying a ``workflow_spec`` in their
``context_config`` (written by the plan card's Save). This router lists them
and re-runs one — identical structure, fresh ephemeral sub-agents — attached
to an existing session or a throwaway one.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config.flags import sessions_enabled
from app.routers.auth import get_current_user
from app.services import sessions as session_svc
from app.services.orchestration import runner
from app.services.rate_limiter import limiter

router = APIRouter(tags=["workflows"])


def _require_flag() -> None:
    if not sessions_enabled():
        raise HTTPException(status_code=404, detail="Sessions are not enabled (FORGE_SESSIONS)")


class SavedWorkflowRun(BaseModel):
    session_id: str = ""
    goal: str = ""
    confirm: bool = False


@router.get("/workflows")
async def list_workflows(user: Any = Depends(get_current_user)):  # noqa: B008
    """List workflows saved to the blueprint library."""
    _require_flag()
    return runner.list_saved_workflows(user.id)


@router.post("/workflows/{workflow_id}/run")
@limiter.limit("30/hour")
async def run_saved_workflow(
    request: Request, workflow_id: str, body: SavedWorkflowRun,
    user: Any = Depends(get_current_user),  # noqa: B008
):
    """Re-run a saved workflow (SSE progress stream)."""
    from app.db import get_db
    from app.kernel.serialize import workflow_spec_from_dict

    _require_flag()
    result = (
        get_db().table("blueprints").select("*").eq("id", workflow_id).execute()
    )
    rows = result.data if isinstance(result.data, list) else []
    row = rows[0] if rows else None
    if row is None or row.get("user_id") != user.id:
        raise HTTPException(status_code=404, detail="Workflow not found")
    cc = row.get("context_config") or {}
    if isinstance(cc, str):
        try:
            cc = json.loads(cc)
        except (TypeError, ValueError):
            cc = {}
    spec_dict = cc.get("workflow_spec") if isinstance(cc, dict) else None
    if not isinstance(spec_dict, dict):
        raise HTTPException(status_code=422, detail="Blueprint has no workflow_spec")

    agent_count = workflow_spec_from_dict(spec_dict).agent_count
    if agent_count > runner.confirm_threshold() and not body.confirm:
        raise HTTPException(
            status_code=400,
            detail=(
                f"This workflow spawns {agent_count} agents (threshold "
                f"{runner.confirm_threshold()}); re-send with confirm=true."
            ),
        )

    if body.session_id:
        session = session_svc.get_session(body.session_id, user.id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session = session_svc.create_session(
            user.id, title=f"Workflow: {row.get('name', '')}"
        )

    async def event_stream():
        async for event in runner.run_workflow(session, spec_dict, goal=body.goal):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
