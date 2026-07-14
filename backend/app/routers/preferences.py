"""User preferences API — defaults + onboarding state + custom instructions."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.db import get_db
from app.routers.auth import get_current_user

router = APIRouter(tags=["preferences"])

# Keep tailoring text bounded so it can't blow up every prompt it's woven into.
MAX_CUSTOM_INSTRUCTIONS = 4000


class PreferencesUpdate(BaseModel):
    default_model: str | None = None
    default_provider: str | None = None
    use_case: str | None = None
    custom_instructions: str | None = None
    onboarded_at: str | None = None
    getting_started_dismissed: bool | None = None
    # harness-plan.md Phase 7 — cost controls + provider fallback policy.
    daily_budget_usd: float | None = None
    fallback_policy_json: dict | None = None


def _get_or_create(user_id: str) -> dict:
    """Return the user's preferences row, creating a default one if absent."""
    result = get_db().table("user_preferences").select("*").eq("user_id", user_id).execute()
    rows = result.data or []
    if rows:
        return dict(rows[0])

    created = get_db().table("user_preferences").insert({"user_id": user_id}).execute()
    if created.data:
        return dict(created.data[0])
    # Fall back to a read in case insert returns nothing on this backend.
    fallback = get_db().table("user_preferences").select("*").eq("user_id", user_id).single().execute()
    return dict(fallback.data)


@router.get("/preferences")
async def get_preferences(user=Depends(get_current_user)):  # noqa: B008
    """Return the user's preferences, auto-creating the row on first read."""
    return _get_or_create(user.id)


@router.put("/preferences")
async def update_preferences(
    body: PreferencesUpdate,
    user=Depends(get_current_user),  # noqa: B008
):
    """Patch any subset of the user's preferences."""
    _get_or_create(user.id)  # ensure the row exists

    patch = body.model_dump(exclude_none=True)
    if "custom_instructions" in patch and patch["custom_instructions"]:
        patch["custom_instructions"] = patch["custom_instructions"][:MAX_CUSTOM_INSTRUCTIONS]
    patch["updated_at"] = datetime.now(UTC).isoformat()

    get_db().table("user_preferences").update(patch).eq("user_id", user.id).execute()
    return _get_or_create(user.id)


def mark_onboarded(user_id: str) -> None:
    """Set onboarded_at = now for a user (used by the onboarding finish flow)."""
    _get_or_create(user_id)
    get_db().table("user_preferences").update(
        {"onboarded_at": datetime.now(UTC).isoformat(), "updated_at": datetime.now(UTC).isoformat()}
    ).eq("user_id", user_id).execute()
