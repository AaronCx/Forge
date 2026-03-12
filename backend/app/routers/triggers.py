"""Trigger management and webhook receiver API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.mcp.scheduler import CronScheduler
from app.mcp.triggers import trigger_service
from app.routers.auth import get_current_user

router = APIRouter(tags=["triggers"])


class TriggerCreateRequest(BaseModel):
    type: str = Field(..., pattern="^(webhook|cron|mcp_event)$")
    config: dict[str, Any] = Field(default_factory=dict)
    target_type: str = Field(..., pattern="^(agent|blueprint)$")
    target_id: str


class TriggerUpdateRequest(BaseModel):
    config: dict[str, Any] | None = None
    enabled: bool | None = None


# --- Trigger CRUD ---


@router.post("/triggers")
async def create_trigger(
    req: TriggerCreateRequest, user: Any = Depends(get_current_user)  # noqa: B008
) -> dict[str, Any]:
    """Create a trigger."""
    # Validate cron expression if applicable
    if req.type == "cron":
        cron_expr = req.config.get("cron_expression", "")
        if not cron_expr or not CronScheduler.validate_cron(cron_expr):
            raise HTTPException(
                status_code=400,
                detail="Invalid or missing cron_expression in config",
            )

    result = await trigger_service.create_trigger(
        user_id=user.id,
        trigger_type=req.type,
        config=req.config,
        target_type=req.target_type,
        target_id=req.target_id,
    )
    return result


@router.get("/triggers")
async def list_triggers(
    user: Any = Depends(get_current_user),  # noqa: B008
) -> list[dict[str, Any]]:
    """List user's triggers."""
    return await trigger_service.list_triggers(user.id)


@router.put("/triggers/{trigger_id}")
async def update_trigger(
    trigger_id: str,
    req: TriggerUpdateRequest,
    user: Any = Depends(get_current_user)  # noqa: B008,
) -> dict[str, Any]:
    """Update a trigger's config or enabled state."""
    trigger = await trigger_service.get_trigger(trigger_id)
    if not trigger or trigger["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Trigger not found")

    updates: dict[str, Any] = {}
    if req.config is not None:
        updates["config"] = req.config
    if req.enabled is not None:
        updates["enabled"] = req.enabled

    result = await trigger_service.update_trigger(trigger_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return result


@router.delete("/triggers/{trigger_id}")
async def delete_trigger(
    trigger_id: str, user: Any = Depends(get_current_user)  # noqa: B008
) -> dict[str, str]:
    """Delete a trigger."""
    trigger = await trigger_service.get_trigger(trigger_id)
    if not trigger or trigger["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Trigger not found")

    await trigger_service.delete_trigger(trigger_id)
    return {"status": "deleted"}


@router.put("/triggers/{trigger_id}/toggle")
async def toggle_trigger(
    trigger_id: str, user: Any = Depends(get_current_user)  # noqa: B008
) -> dict[str, Any]:
    """Toggle a trigger's enabled state."""
    trigger = await trigger_service.get_trigger(trigger_id)
    if not trigger or trigger["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Trigger not found")

    result = await trigger_service.toggle_trigger(trigger_id)
    if not result:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return result


@router.get("/triggers/{trigger_id}/history")
async def trigger_history(
    trigger_id: str,
    limit: int = 20,
    user: Any = Depends(get_current_user)  # noqa: B008,
) -> list[dict[str, Any]]:
    """Get recent trigger firings."""
    trigger = await trigger_service.get_trigger(trigger_id)
    if not trigger or trigger["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Trigger not found")

    return await trigger_service.get_trigger_history(trigger_id, limit)


# --- Webhook Receiver ---


@router.post("/webhooks/{trigger_id}")
async def webhook_receiver(trigger_id: str, request: Request) -> dict[str, Any]:
    """Webhook endpoint that external services hit to fire a trigger.

    No authentication required — the trigger ID acts as the secret URL.
    Optionally verify webhook_secret from query params or headers.
    """
    trigger = await trigger_service.get_trigger(trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if trigger["type"] != "webhook":
        raise HTTPException(status_code=400, detail="Not a webhook trigger")
    if not trigger.get("enabled", True):
        raise HTTPException(status_code=403, detail="Webhook is disabled")

    # Optional secret verification
    config = trigger.get("config", {})
    expected_secret = config.get("webhook_secret")
    if expected_secret:
        provided_secret = request.query_params.get(
            "secret", request.headers.get("x-webhook-secret", "")
        )
        if provided_secret != expected_secret:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

    # Parse request body
    try:
        payload = await request.json()
    except Exception:
        payload = {"raw": (await request.body()).decode("utf-8", errors="replace")}

    result = await trigger_service.fire_trigger(trigger_id, payload)
    return result
