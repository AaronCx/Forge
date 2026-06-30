"""Shared document text extraction.

Factored out of the ``fetch_document`` blueprint node and the
``document_reader`` LangChain tool so the agent runner and blueprint nodes
share a single extractor (dashboard composer spec, PR-1). Supports remote
documents (``http``/``https``) and local files (``file://`` URIs or bare
filesystem paths) produced by the uploads storage backend (PR-2).
"""

from __future__ import annotations

import io
from pathlib import Path
from urllib.parse import unquote, urlparse

from docx import Document
from pypdf import PdfReader

from app.services import storage
from app.services.security.url_validator import safe_get, validate_url

# Cap extracted text so a large upload can't blow up a prompt/context window.
MAX_CHARS = 10_000


async def extract_text(file_url: str) -> str:
    """Read a document from ``file_url`` and return its extracted plain text.

    Handles PDF, DOCX, and plain-text/markdown. Returns at most
    :data:`MAX_CHARS` characters. Raises on download/read failure — callers
    that need graceful degradation (the tool wrapper, the agent runner) catch
    and substitute a note.
    """
    file_bytes, content_type, name = await _load(file_url)
    lowered = name.lower()

    if "pdf" in content_type or lowered.endswith(".pdf"):
        return _extract_pdf(file_bytes)
    if "wordprocessingml" in content_type or lowered.endswith(".docx"):
        return _extract_docx(file_bytes)
    # Plain text, markdown, or unknown — decode best-effort.
    return file_bytes.decode("utf-8", errors="replace")[:MAX_CHARS]


async def _load(file_url: str) -> tuple[bytes, str, str]:
    """Return ``(bytes, content_type, name)`` for a remote or local document."""
    parsed = urlparse(file_url)

    if parsed.scheme in ("http", "https"):
        validate_url(file_url)  # SSRF guard — blocks internal/private targets
        # safe_get re-validates each redirect hop (no public→internal 302 bypass).
        response = await safe_get(file_url, timeout=30.0)
        response.raise_for_status()
        return response.content, response.headers.get("content-type", ""), parsed.path

    if parsed.scheme not in ("", "file"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

    # Local file: a ``file://`` URI or a bare filesystem path. Only files the
    # uploads storage backend wrote (inside the upload dir) may be read back —
    # anything else is an arbitrary-local-file-read primitive.
    path = Path(unquote(parsed.path)) if parsed.scheme == "file" else Path(file_url)
    resolved = path.resolve()
    if not resolved.is_relative_to(storage.upload_dir().resolve()):
        raise ValueError("Local file access is restricted to the upload directory")
    return resolved.read_bytes(), "", resolved.name


def _extract_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    parts = [page.extract_text() for page in reader.pages]
    return "\n\n".join(text for text in parts if text)[:MAX_CHARS]


def _extract_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(parts)[:MAX_CHARS]
