"""PR-6 — voice transcription endpoint (Whisper via the user's OpenAI key)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


def _auth(mock_db):
    mock_user = MagicMock()
    mock_user.user = MagicMock(id="user-1")
    mock_db.auth.get_user.return_value = mock_user


def test_transcribe_returns_text(client):
    fake_result = MagicMock(text="summarize the latest run failures")
    fake_client = MagicMock()
    fake_client.audio.transcriptions.create = AsyncMock(return_value=fake_result)

    with patch("app.db._db") as mock_db, \
         patch("app.routers.transcribe.get_user_openai_key", new=AsyncMock(return_value="sk-test")), \
         patch("openai.AsyncOpenAI", return_value=fake_client):
        _auth(mock_db)
        resp = client.post(
            "/api/transcribe?token=t",
            files=[("file", ("audio.webm", b"fake-audio-bytes", "audio/webm"))],
        )

    assert resp.status_code == 200
    assert resp.json()["text"] == "summarize the latest run failures"


def test_transcribe_400_without_openai_key(client):
    with patch("app.db._db") as mock_db, \
         patch("app.routers.transcribe.get_user_openai_key", new=AsyncMock(return_value=None)):
        _auth(mock_db)
        resp = client.post(
            "/api/transcribe?token=t",
            files=[("file", ("audio.webm", b"fake-audio-bytes", "audio/webm"))],
        )

    assert resp.status_code == 400
    assert "OpenAI" in resp.json()["detail"]


def test_transcribe_rejects_empty_audio(client):
    with patch("app.db._db") as mock_db, \
         patch("app.routers.transcribe.get_user_openai_key", new=AsyncMock(return_value="sk-test")):
        _auth(mock_db)
        resp = client.post(
            "/api/transcribe?token=t",
            files=[("file", ("audio.webm", b"", "audio/webm"))],
        )

    assert resp.status_code == 400


def test_transcribe_rejects_bad_token(client):
    with patch("app.db._db") as mock_db:
        mock_db.auth.get_user.side_effect = Exception("nope")
        resp = client.post(
            "/api/transcribe?token=bad",
            files=[("file", ("audio.webm", b"x", "audio/webm"))],
        )
    assert resp.status_code == 401
