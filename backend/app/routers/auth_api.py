"""Auth API endpoints for local mode (signup, login, me).

These work with the local JWT auth backend (SQLite mode).
For Supabase mode, auth is handled client-side via Supabase Auth.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import get_db
from app.routers.auth import get_current_user

router = APIRouter(tags=["auth"])


class AuthRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)


class AuthResponse(BaseModel):
    access_token: str
    user_id: str
    email: str


class UserInfo(BaseModel):
    id: str
    email: str


@router.post("/auth/signup", response_model=AuthResponse)
async def signup(req: AuthRequest):
    """Create a local account."""
    db = get_db()

    # Check if local auth is available
    from app.db.sqlite_backend import SQLiteBackend
    if not isinstance(db, SQLiteBackend):
        raise HTTPException(status_code=400, detail="Local signup not available in Supabase mode")

    # Check if email already exists
    existing = db.table("local_users").select("id").eq("email", req.email).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Hash password
    import bcrypt
    password_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()

    user_id = str(uuid.uuid4())
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    db.table("local_users").insert({
        "id": user_id,
        "email": req.email,
        "password_hash": password_hash,
        "created_at": now,
    }).execute()

    # Generate JWT
    import jwt as pyjwt
    token = pyjwt.encode(
        {"sub": user_id, "email": req.email},
        db.auth._jwt_secret,
        algorithm="HS256",
    )

    return AuthResponse(access_token=token, user_id=user_id, email=req.email)


@router.post("/auth/login", response_model=AuthResponse)
async def login(req: AuthRequest):
    """Login with email/password and get a JWT."""
    db = get_db()

    from app.db.sqlite_backend import SQLiteBackend
    if not isinstance(db, SQLiteBackend):
        raise HTTPException(status_code=400, detail="Local login not available in Supabase mode")

    # Look up user
    result = db.table("local_users").select("*").eq("email", req.email).single().execute()
    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Verify password
    import bcrypt
    if not bcrypt.checkpw(req.password.encode(), result.data["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Generate JWT
    import jwt as pyjwt
    token = pyjwt.encode(
        {"sub": result.data["id"], "email": result.data["email"]},
        db.auth._jwt_secret,
        algorithm="HS256",
    )

    return AuthResponse(
        access_token=token,
        user_id=result.data["id"],
        email=result.data["email"],
    )


@router.get("/auth/me", response_model=UserInfo)
async def me(user=Depends(get_current_user)):  # noqa: B008
    """Return current user info."""
    return UserInfo(id=user.id, email=getattr(user, "email", ""))
