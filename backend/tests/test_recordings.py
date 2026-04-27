"""Tests for the recordings listing endpoint."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def test_recordings_requires_auth(client):
    response = client.get("/api/recordings")
    assert response.status_code == 422


def test_recordings_empty_when_storage_missing(auth_client, monkeypatch):
    monkeypatch.setenv("AF_RECORDING_STORAGE", "/nonexistent/path/forge-recordings")
    response = auth_client.get(
        "/api/recordings",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_recordings_lists_files(auth_client, monkeypatch):
    with tempfile.TemporaryDirectory() as storage:
        Path(storage, "Computer-Use-demo__abc123.mp4").write_bytes(b"x" * 64)
        Path(storage, "Test-runner__def456.mp4").write_bytes(b"x" * 32)
        monkeypatch.setenv("AF_RECORDING_STORAGE", storage)

        response = auth_client.get(
            "/api/recordings",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = {entry["id"] for entry in data}
        assert names == {"Computer-Use-demo__abc123.mp4", "Test-runner__def456.mp4"}
        assert all("started_at" in entry for entry in data)
        assert all("size_bytes" in entry for entry in data)
