"""Blueprint API routes — CRUD and execution endpoints."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.db import get_db
from app.models.blueprint import (
    BlueprintCreate,
    BlueprintResponse,
    BlueprintRunRequest,
    BlueprintRunResponse,
    BlueprintUpdate,
)
from app.routers.auth import get_current_user
from app.services.blueprint_engine import blueprint_engine
from app.services.blueprint_nodes.registry import list_node_types
from app.services.rate_limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["blueprints"])


# --- CRUD ---


@router.get("/blueprints", response_model=list[BlueprintResponse])
async def list_blueprints(
    user=Depends(get_current_user),  # noqa: B008
):
    """List user's blueprints."""
    result = (
        get_db().table("blueprints")
        .select("*")
        .eq("user_id", user.id)
        .order("updated_at", desc=True)
        .execute()
    )
    return result.data or []


@router.get("/blueprints/templates", response_model=list[BlueprintResponse])
async def list_blueprint_templates():
    """List pre-built blueprint templates."""
    result = (
        get_db().table("blueprints")
        .select("*")
        .eq("is_template", True)
        .order("name")
        .execute()
    )
    return result.data or []


@router.get("/blueprints/node-types")
async def get_node_types(category: str | None = Query(None)):
    """List available node types, optionally filtered by category."""
    return list_node_types(category)


@router.get("/blueprints/{blueprint_id}", response_model=BlueprintResponse)
async def get_blueprint(
    blueprint_id: str, user=Depends(get_current_user),  # noqa: B008
):
    """Get a blueprint by ID."""
    result = (
        get_db().table("blueprints")
        .select("*")
        .eq("id", blueprint_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    bp = result.data
    if bp["user_id"] != user.id and not bp.get("is_template"):
        raise HTTPException(status_code=404, detail="Blueprint not found")

    return bp


@router.post("/blueprints", response_model=BlueprintResponse, status_code=201)
@limiter.limit("20/hour")
async def create_blueprint(
    bp: BlueprintCreate, request: Request, user=Depends(get_current_user),  # noqa: B008
):
    """Create a new blueprint."""
    data = {
        "user_id": user.id,
        "name": bp.name,
        "description": bp.description,
        "nodes": [n.model_dump() for n in bp.nodes],
        "context_config": bp.context_config,
        "tool_scope": bp.tool_scope,
        "retry_policy": bp.retry_policy,
        "output_schema": bp.output_schema,
    }
    result = get_db().table("blueprints").insert(data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create blueprint")
    return result.data[0]


@router.put("/blueprints/{blueprint_id}", response_model=BlueprintResponse)
async def update_blueprint(
    blueprint_id: str, bp: BlueprintUpdate, user=Depends(get_current_user),  # noqa: B008
):
    """Update a blueprint."""
    # Verify ownership
    existing = (
        get_db().table("blueprints")
        .select("user_id")
        .eq("id", blueprint_id)
        .single()
        .execute()
    )
    if not existing.data or existing.data["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    update_data = bp.model_dump(exclude_none=True)
    if "nodes" in update_data:
        update_data["nodes"] = [
            n if isinstance(n, dict) else n.model_dump() for n in update_data["nodes"]
        ]
    # Bump version
    update_data["version"] = existing.data.get("version", 1) + 1 if existing.data else 1

    result = (
        get_db().table("blueprints")
        .update(update_data)
        .eq("id", blueprint_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update blueprint")
    return result.data[0]


@router.delete("/blueprints/{blueprint_id}", status_code=204)
async def delete_blueprint(
    blueprint_id: str, user=Depends(get_current_user),  # noqa: B008
):
    """Delete a blueprint."""
    existing = (
        get_db().table("blueprints")
        .select("user_id")
        .eq("id", blueprint_id)
        .single()
        .execute()
    )
    if not existing.data or existing.data["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    get_db().table("blueprints").delete().eq("id", blueprint_id).execute()


# --- Execution ---


@router.post("/blueprints/{blueprint_id}/run")
@limiter.limit("10/hour")
async def run_blueprint(
    blueprint_id: str,
    run_req: BlueprintRunRequest,
    request: Request,
    user=Depends(get_current_user),  # noqa: B008
):
    """Execute a blueprint with input payload. Streams progress via SSE."""
    # Load blueprint
    bp_result = (
        get_db().table("blueprints")
        .select("*")
        .eq("id", blueprint_id)
        .single()
        .execute()
    )
    if not bp_result.data:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    blueprint = bp_result.data
    if blueprint["user_id"] != user.id and not blueprint.get("is_template"):
        raise HTTPException(status_code=404, detail="Blueprint not found")

    # Create run record
    input_payload = {
        "text": run_req.input_text,
        **run_req.input_data,
    }
    run_result = get_db().table("blueprint_runs").insert({
        "blueprint_id": blueprint_id,
        "user_id": user.id,
        "status": "running",
        "input_payload": input_payload,
        "started_at": "now()",
    }).execute()

    if not run_result.data:
        raise HTTPException(status_code=500, detail="Failed to create run")

    run_id = run_result.data[0]["id"]

    async def event_stream():
        try:
            async for event in blueprint_engine.execute(
                blueprint=blueprint,
                input_payload=input_payload,
                user_id=user.id,
                run_id=run_id,
            ):
                yield f"data: {json.dumps(event)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("Blueprint execution failed: %s", e)
            get_db().table("blueprint_runs").update({
                "status": "failed",
            }).eq("id", run_id).execute()
            yield f"data: {json.dumps({'type': 'error', 'data': 'Blueprint execution failed'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Run-Id": run_id,
        },
    )


# --- Run history ---


@router.get("/blueprints/runs/{run_id}", response_model=BlueprintRunResponse)
async def get_blueprint_run(
    run_id: str, user=Depends(get_current_user),  # noqa: B008
):
    """Get execution trace for a blueprint run."""
    result = (
        get_db().table("blueprint_runs")
        .select("*")
        .eq("id", run_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Run not found")
    if result.data["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return result.data


@router.get("/blueprints/{blueprint_id}/runs", response_model=list[BlueprintRunResponse])
async def list_blueprint_runs(
    blueprint_id: str,
    limit: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),  # noqa: B008
):
    """List runs for a specific blueprint."""
    result = (
        get_db().table("blueprint_runs")
        .select("*")
        .eq("blueprint_id", blueprint_id)
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []
