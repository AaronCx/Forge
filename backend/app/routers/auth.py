from fastapi import Header, HTTPException

from app.db import get_db


async def get_current_user(authorization: str = Header(...)):
    """Extract and verify user from JWT (works with both Supabase and local auth)."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.removeprefix("Bearer ")

    try:
        user_response = get_db().auth.get_user(token)
        # Supabase returns response.user, local auth returns user directly
        user = user_response.user if hasattr(user_response, "user") else user_response
        if not user or not getattr(user, "id", None):
            raise HTTPException(status_code=401, detail="Invalid token")
        return user
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
