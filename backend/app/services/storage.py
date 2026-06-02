"""Upload storage abstraction — env-driven local-dir or Supabase-bucket.

Mirrors the recordings pattern (``recordings.py`` reads ``AF_RECORDING_STORAGE``):
local mode writes to ``AF_UPLOAD_DIR`` (default ``/tmp/forge-uploads``); when the
Supabase backend is active, files go to the ``forge-uploads`` Storage bucket.

Locally-stored **images** are returned as base64 ``data:`` URLs so a remote
vision model can receive the bytes inline (a ``file://`` path or ``localhost``
URL is unreachable from the provider). **Documents** are returned as
``file://`` paths the server reads back through ``services.extract`` and never
hands to a model as a URL.
"""

from __future__ import annotations

import base64
import os
import uuid
from pathlib import Path

BUCKET = "forge-uploads"

# Allowlisted MIME types. Anything else is rejected by the uploads endpoint
# with HTTP 415.
DOCUMENT_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
}


def kind_for_mime(mime: str) -> str | None:
    """Map a MIME type to an attachment ``kind`` (``image``/``document``).

    Returns ``None`` for unsupported types so the caller can reject with 415.
    """
    mime = (mime or "").split(";", 1)[0].strip().lower()
    if mime.startswith("image/"):
        return "image"
    if mime in DOCUMENT_MIMES or mime == "text/x-markdown":
        return "document"
    return None


def use_supabase() -> bool:
    """True when uploads should target Supabase Storage rather than local disk."""
    backend = os.getenv("FORGE_DB_BACKEND", "").lower()
    if backend == "supabase":
        return True
    if backend == "sqlite":
        return False
    # Auto: match create_db_from_env — Supabase if its env is configured.
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"))


def upload_dir() -> Path:
    """The local upload directory, created on first use."""
    d = Path(os.getenv("AF_UPLOAD_DIR", "/tmp/forge-uploads"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(file_bytes: bytes, filename: str, mime: str, user_id: str) -> dict:
    """Persist a file and return an ``Attachment`` dict.

    Raises ``ValueError`` for unsupported MIME types (caller maps to 415).
    """
    kind = kind_for_mime(mime)
    if kind is None:
        raise ValueError(f"Unsupported file type: {mime}")

    file_id = uuid.uuid4().hex
    safe_name = Path(filename or "").name or file_id

    if use_supabase():
        url = _save_supabase(file_id, safe_name, file_bytes, mime, user_id)
    else:
        url = _save_local(file_id, safe_name, file_bytes, mime, kind)

    return {"id": file_id, "url": url, "kind": kind, "name": safe_name, "mime": mime}


def get_url(ref: str) -> str:
    """Resolve a stored ref to a usable URL.

    ``ref`` may already be a usable URL (``http(s)``/``data:``/``file://``) — in
    which case it's returned unchanged — or a local ``{id}__{name}`` key, which
    is resolved against the upload directory.
    """
    if ref.startswith(("http://", "https://", "data:", "file://")):
        return ref
    if use_supabase():
        return f"{os.environ['SUPABASE_URL']}/storage/v1/object/public/{BUCKET}/{ref}"  # lastgate-ignore: public URL, not a secret
    return (upload_dir() / ref).as_uri()


def _save_local(file_id: str, name: str, data: bytes, mime: str, kind: str) -> str:
    path = upload_dir() / f"{file_id}__{name}"
    path.write_bytes(data)
    if kind == "image":
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    return path.as_uri()


def _save_supabase(file_id: str, name: str, data: bytes, mime: str, user_id: str) -> str:
    from supabase import create_client

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    key = f"{user_id}/{file_id}__{name}"
    bucket = client.storage.from_(BUCKET)
    # The forge-uploads bucket must exist and be public (created via the
    # Supabase dashboard/migrations). upsert avoids collisions on retry.
    bucket.upload(key, data, {"content-type": mime, "upsert": "true"})
    return str(bucket.get_public_url(key))
