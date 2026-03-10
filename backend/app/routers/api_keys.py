import hashlib
import secrets
from fastapi import APIRouter, Depends, HTTPException
from app.routers.auth import get_current_user
from app.models.user import ApiKeyCreate, ApiKeyResponse
from app.database import supabase

router = APIRouter(tags=["api_keys"])


@router.get("/keys", response_model=list[ApiKeyResponse])
async def list_keys(user=Depends(get_current_user)):
    result = supabase.table("api_keys").select("id, name, created_at, last_used_at").eq("user_id", user.id).execute()
    return result.data


@router.post("/keys")
async def create_key(body: ApiKeyCreate, user=Depends(get_current_user)):
    raw_key = f"af_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    supabase.table("api_keys").insert({
        "user_id": user.id,
        "name": body.name,
        "key_hash": key_hash,
    }).execute()

    return {"key": raw_key}


@router.delete("/keys/{key_id}", status_code=204)
async def delete_key(key_id: str, user=Depends(get_current_user)):
    existing = supabase.table("api_keys").select("user_id").eq("id", key_id).single().execute()
    if not existing.data or existing.data["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="API key not found")

    supabase.table("api_keys").delete().eq("id", key_id).execute()
