import contextlib
import hashlib
from datetime import UTC, datetime

from fastapi import Header, HTTPException

from app.db import get_db


class _ApiKeyUser:
    """Minimal user object for API-key auth — routers only read ``.id``."""

    def __init__(self, user_id: str):
        self.id = user_id


async def get_current_user(authorization: str = Header(...)):
    """Extract and verify the user from a Bearer token.

    Accepts both a JWT (Supabase or local auth) and a Forge API key (``af_``
    prefix), so the CLI/MCP key flow actually authenticates.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.removeprefix("Bearer ")

    # Forge API keys: the raw key is never stored — match its SHA-256 against
    # api_keys.key_hash (indexed lookup, so no timing side-channel).
    if token.startswith("af_"):
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        try:
            result = (
                get_db().table("api_keys")
                .select("id, user_id")
                .eq("key_hash", key_hash)
                .single()
                .execute()
            )
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid API key") from exc
        if not result.data or not result.data.get("user_id"):
            raise HTTPException(status_code=401, detail="Invalid API key")
        with contextlib.suppress(Exception):
            get_db().table("api_keys").update(
                {"last_used_at": datetime.now(UTC).isoformat()}
            ).eq("id", result.data["id"]).execute()
        return _ApiKeyUser(result.data["user_id"])

    try:
        user_response = get_db().auth.get_user(token)
        # Supabase returns response.user, local auth returns user directly
        user = user_response.user if hasattr(user_response, "user") else user_response
        if not user or not getattr(user, "id", None):
            raise HTTPException(status_code=401, detail="Invalid token")
        return user
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
