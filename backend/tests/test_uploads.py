"""PR-2 — uploads endpoint + storage abstraction.

Covers MIME→kind inference, local save (data URL for images, file:// for
documents), and the endpoint's type/size guardrails.
"""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

from app.services import storage


# --- MIME → kind --------------------------------------------------------------


def test_kind_for_mime_images():
    assert storage.kind_for_mime("image/png") == "image"
    assert storage.kind_for_mime("image/jpeg") == "image"
    assert storage.kind_for_mime("image/webp") == "image"


def test_kind_for_mime_documents():
    assert storage.kind_for_mime("application/pdf") == "document"
    assert storage.kind_for_mime("text/plain") == "document"
    assert storage.kind_for_mime("text/markdown") == "document"
    assert (
        storage.kind_for_mime(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        == "document"
    )


def test_kind_for_mime_strips_charset_params():
    assert storage.kind_for_mime("text/plain; charset=utf-8") == "document"


def test_kind_for_mime_rejects_unknown():
    assert storage.kind_for_mime("video/mp4") is None
    assert storage.kind_for_mime("application/zip") is None
    assert storage.kind_for_mime("") is None


# --- Local save ---------------------------------------------------------------


def test_save_image_returns_data_url(tmp_path, monkeypatch):
    monkeypatch.setenv("AF_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("FORGE_DB_BACKEND", "sqlite")

    raw = b"\x89PNG\r\n\x1a\n fake image bytes"
    ref = storage.save(raw, "shot.png", "image/png", "user-1")

    assert ref["kind"] == "image"
    assert ref["name"] == "shot.png"
    assert ref["url"].startswith("data:image/png;base64,")
    decoded = base64.b64decode(ref["url"].split(",", 1)[1])
    assert decoded == raw


def test_save_document_returns_file_uri(tmp_path, monkeypatch):
    monkeypatch.setenv("AF_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("FORGE_DB_BACKEND", "sqlite")

    ref = storage.save(b"hello document", "notes.txt", "text/plain", "user-1")

    assert ref["kind"] == "document"
    assert ref["url"].startswith("file://")
    # File is on disk under the upload dir with an id-prefixed name.
    written = list(tmp_path.iterdir())
    assert len(written) == 1
    assert written[0].read_bytes() == b"hello document"


def test_save_rejects_unsupported_mime(tmp_path, monkeypatch):
    monkeypatch.setenv("AF_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("FORGE_DB_BACKEND", "sqlite")

    try:
        storage.save(b"x", "clip.mp4", "video/mp4", "user-1")
    except ValueError as exc:
        assert "Unsupported" in str(exc)
    else:  # pragma: no cover - guard
        raise AssertionError("expected ValueError for unsupported mime")


def test_get_url_passthrough():
    assert storage.get_url("https://x/y.png") == "https://x/y.png"
    assert storage.get_url("data:image/png;base64,AAAA") == "data:image/png;base64,AAAA"
    assert storage.get_url("file:///tmp/a.txt") == "file:///tmp/a.txt"


def test_use_supabase_env_switch(monkeypatch):
    monkeypatch.setenv("FORGE_DB_BACKEND", "supabase")
    assert storage.use_supabase() is True
    monkeypatch.setenv("FORGE_DB_BACKEND", "sqlite")
    assert storage.use_supabase() is False


# --- Endpoint guardrails ------------------------------------------------------


def _auth(mock_db):
    mock_user = MagicMock()
    mock_user.user = MagicMock(id="user-1")
    mock_db.auth.get_user.return_value = mock_user


def test_upload_endpoint_returns_refs(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AF_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("FORGE_DB_BACKEND", "sqlite")

    with patch("app.db._db") as mock_db:
        _auth(mock_db)
        resp = client.post(
            "/api/uploads?token=t",
            files=[
                ("files", ("a.txt", b"hello", "text/plain")),
                ("files", ("b.png", b"\x89PNG bytes", "image/png")),
            ],
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["kind"] == "document"
    assert data[1]["kind"] == "image"


def test_upload_endpoint_rejects_unsupported_type(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AF_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("FORGE_DB_BACKEND", "sqlite")

    with patch("app.db._db") as mock_db:
        _auth(mock_db)
        resp = client.post(
            "/api/uploads?token=t",
            files=[("files", ("clip.mp4", b"x", "video/mp4"))],
        )

    assert resp.status_code == 415


def test_upload_endpoint_rejects_oversize(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AF_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setenv("FORGE_DB_BACKEND", "sqlite")

    big = b"x" * (25 * 1024 * 1024 + 1)  # 25MB + 1 byte
    with patch("app.db._db") as mock_db:
        _auth(mock_db)
        resp = client.post(
            "/api/uploads?token=t",
            files=[("files", ("big.txt", big, "text/plain"))],
        )

    assert resp.status_code == 413


def test_upload_endpoint_rejects_bad_token(client):
    with patch("app.db._db") as mock_db:
        mock_db.auth.get_user.side_effect = Exception("nope")
        resp = client.post(
            "/api/uploads?token=bad",
            files=[("files", ("a.txt", b"hello", "text/plain"))],
        )

    assert resp.status_code == 401
