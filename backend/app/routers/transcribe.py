"""Voice transcription endpoint — Whisper via the user's existing OpenAI key."""

import io

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from app.db import get_db
from app.services.llm import get_user_openai_key
from app.services.rate_limiter import limiter

router = APIRouter(tags=["transcribe"])

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # OpenAI's audio upload cap


@router.post("/transcribe")
@limiter.limit("60/hour")
async def transcribe(
    request: Request,
    token: str = Query(...),
    file: UploadFile = File(...),  # noqa: B008
):
    """Transcribe an uploaded audio clip to text via OpenAI Whisper."""
    # Verify token (dual Supabase/SQLite unwrap).
    try:
        user_response = get_db().auth.get_user(token)
        user = user_response.user if hasattr(user_response, "user") else user_response
        if not user or not getattr(user, "id", None):
            raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    api_key = await get_user_openai_key(user.id)
    if not api_key:
        raise HTTPException(status_code=400, detail="Connect an OpenAI provider to use voice.")

    data = await file.read()
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio clip is too large.")
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio upload.")

    from openai import AsyncOpenAI

    audio = io.BytesIO(data)
    audio.name = file.filename or "audio.webm"
    try:
        client = AsyncOpenAI(api_key=api_key)
        result = await client.audio.transcriptions.create(model="whisper-1", file=audio)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Transcription failed.") from exc

    return {"text": getattr(result, "text", "")}
