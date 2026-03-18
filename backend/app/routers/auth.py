from fastapi import Header, HTTPException

from app.db import get_db


async def get_current_user(authorization: str = Header(...)):
    """Extract and verify user from Supabase JWT."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization.removeprefix("Bearer ")

    try:
        user_response = get_db().auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_response.user
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
