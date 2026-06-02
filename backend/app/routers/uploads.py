"""File upload endpoint — accepts browser files, returns stable Attachment refs."""

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from app.db import get_db
from app.models.attachment import Attachment
from app.services import storage
from app.services.rate_limiter import limiter

router = APIRouter(tags=["uploads"])

# Guardrails: cap per-file size; type is enforced by storage.kind_for_mime.
MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB


@router.post("/uploads", response_model=list[Attachment])
@limiter.limit("60/hour")
async def upload_files(
    request: Request,
    token: str = Query(...),
    files: list[UploadFile] = File(...),  # noqa: B008
):
    """Accept one or more files (multipart) and return Attachment refs."""
    # Verify token. The auth backend returns either a Supabase-style wrapper
    # (`.user`) or the user object directly (SQLite local auth) — handle both.
    try:
        user_response = get_db().auth.get_user(token)
        user = user_response.user if hasattr(user_response, "user") else user_response
        if not user or not getattr(user, "id", None):
            raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    results: list[dict] = []
    for upload in files:
        data = await upload.read()
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"{upload.filename or 'file'} exceeds the {MAX_FILE_BYTES // (1024 * 1024)}MB limit",  # lastgate-ignore: f-string, not a secret
            )
        mime = upload.content_type or "application/octet-stream"
        if storage.kind_for_mime(mime) is None:
            raise HTTPException(status_code=415, detail=f"Unsupported file type: {mime}")
        try:
            results.append(storage.save(data, upload.filename or "upload", mime, user.id))
        except ValueError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc

    return results
