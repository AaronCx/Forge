"""Tests for observability: trace service, prompt versions, API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.observability.prompt_versions import PromptVersionService
from app.services.observability.trace_service import TraceService

# === Trace Service tests ===


@pytest.mark.asyncio
async def test_record_span():
    service = TraceService()
    mock_result = MagicMock()
    mock_result.data = [{
        "id": "t1", "user_id": "u1", "span_type": "agent_step",
        "span_name": "Step 1", "status": "ok", "input_tokens": 100,
        "output_tokens": 50, "latency_ms": 500.0,
    }]

    with patch("app.db._db") as mock_sb:
        mock_sb.table.return_value.insert.return_value.execute.return_value = mock_result
        result = await service.record_span(
            user_id="u1",
            span_type="agent_step",
            span_name="Step 1",
            run_id="r1",
            model="gpt-4o-mini",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            latency_ms=500.0,
        )

    assert result["span_type"] == "agent_step"
    assert result["input_tokens"] == 100


@pytest.mark.asyncio
async def test_start_and_end_span():
    service = TraceService()

    mock_start = MagicMock()
    mock_start.data = [{
        "id": "t1", "user_id": "u1", "span_type": "llm_call",
        "span_name": "Test", "status": "running",
    }]

    mock_end = MagicMock()
    mock_end.data = [{
        "id": "t1", "status": "ok", "input_tokens": 200,
        "output_tokens": 100, "latency_ms": 300.0,
    }]

    with patch("app.db._db") as mock_sb:
        mock_sb.table.return_value.insert.return_value.execute.return_value = mock_start
        span = await service.start_span(
            user_id="u1", span_type="llm_call", span_name="Test",
        )
        assert span["status"] == "running"

        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_end
        ended = await service.end_span(
            "t1", status="ok", input_tokens=200, output_tokens=100, latency_ms=300.0,
        )
        assert ended is not None
        assert ended["status"] == "ok"


@pytest.mark.asyncio
async def test_list_traces():
    service = TraceService()
    mock_result = MagicMock()
    mock_result.data = [
        {"id": "t1", "span_type": "agent_step"},
        {"id": "t2", "span_type": "llm_call"},
    ]

    with patch("app.db._db") as mock_sb:
        query = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value = query
        query.order.return_value.range.return_value.execute.return_value = mock_result
        result = await service.list_traces("u1")

    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_trace():
    service = TraceService()
    mock_result = MagicMock()
    mock_result.data = {"id": "t1", "span_type": "agent_step", "user_id": "u1"}

    with patch("app.db._db") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_result
        result = await service.get_trace("t1", "u1")

    assert result is not None
    assert result["id"] == "t1"


@pytest.mark.asyncio
async def test_get_trace_tree():
    service = TraceService()

    mock_parent = MagicMock()
    mock_parent.data = {"id": "t1", "span_type": "agent_step", "user_id": "u1"}

    mock_children = MagicMock()
    mock_children.data = [
        {"id": "t2", "span_type": "llm_call", "parent_span_id": "t1"},
    ]

    with patch("app.db._db") as mock_sb:
        # get_trace call
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_parent
        # children call
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = mock_children

        result = await service.get_trace_tree("t1", "u1")

    assert result.get("children") is not None
    assert len(result["children"]) == 1


@pytest.mark.asyncio
async def test_trace_stats():
    service = TraceService()
    mock_result = MagicMock()
    mock_result.data = [
        {"span_type": "agent_step", "status": "ok", "input_tokens": 100, "output_tokens": 50, "latency_ms": 500},
        {"span_type": "llm_call", "status": "error", "input_tokens": 200, "output_tokens": 0, "latency_ms": 1000},
        {"span_type": "agent_step", "status": "ok", "input_tokens": 150, "output_tokens": 75, "latency_ms": 300},
    ]

    with patch("app.db._db") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_result
        stats = await service.get_trace_stats("u1")

    assert stats["total_spans"] == 3
    assert stats["error_count"] == 1
    assert stats["total_tokens"] == 575
    assert stats["by_type"]["agent_step"] == 2
    assert stats["by_type"]["llm_call"] == 1


# === Prompt Version Service tests ===


@pytest.mark.asyncio
async def test_create_first_version():
    service = PromptVersionService()

    mock_prev = MagicMock()
    mock_prev.data = []  # no previous versions

    mock_insert = MagicMock()
    mock_insert.data = [{
        "id": "v1", "agent_id": "a1", "version_number": 1,
        "system_prompt": "You are a helper.", "is_active": True,
        "change_summary": "Initial version",
    }]

    with patch("app.db._db") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_prev
        mock_sb.table.return_value.insert.return_value.execute.return_value = mock_insert

        result = await service.create_version(
            user_id="u1", agent_id="a1",
            system_prompt="You are a helper.",
            change_summary="Initial version",
        )

    assert result["version_number"] == 1
    assert result["is_active"] is True


@pytest.mark.asyncio
async def test_create_subsequent_version():
    service = PromptVersionService()

    mock_prev = MagicMock()
    mock_prev.data = [{
        "id": "v1", "version_number": 1, "system_prompt": "Old prompt",
        "is_active": True,
    }]

    mock_deactivate = MagicMock()
    mock_deactivate.data = [{"id": "v1", "is_active": False}]

    mock_insert = MagicMock()
    mock_insert.data = [{
        "id": "v2", "agent_id": "a1", "version_number": 2,
        "system_prompt": "New prompt", "is_active": True,
        "diff_from_previous": "--- previous\n+++ current\n-Old prompt\n+New prompt\n",
    }]

    with patch("app.db._db") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_prev
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_deactivate
        mock_sb.table.return_value.insert.return_value.execute.return_value = mock_insert

        result = await service.create_version(
            user_id="u1", agent_id="a1",
            system_prompt="New prompt",
        )

    assert result["version_number"] == 2


@pytest.mark.asyncio
async def test_list_versions():
    service = PromptVersionService()
    mock_result = MagicMock()
    mock_result.data = [
        {"id": "v2", "version_number": 2, "is_active": True},
        {"id": "v1", "version_number": 1, "is_active": False},
    ]

    with patch("app.db._db") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_result
        result = await service.list_versions("a1", "u1")

    assert len(result) == 2
    assert result[0]["version_number"] == 2


@pytest.mark.asyncio
async def test_rollback():
    service = PromptVersionService()

    # get_version
    mock_target = MagicMock()
    mock_target.data = {
        "id": "v1", "agent_id": "a1", "version_number": 1,
        "system_prompt": "Original prompt", "user_id": "u1",
    }

    # create_version internals
    mock_prev = MagicMock()
    mock_prev.data = [{"id": "v2", "version_number": 2, "system_prompt": "New prompt", "is_active": True}]

    mock_deactivate = MagicMock()
    mock_deactivate.data = [{"id": "v2", "is_active": False}]

    mock_insert = MagicMock()
    mock_insert.data = [{
        "id": "v3", "agent_id": "a1", "version_number": 3,
        "system_prompt": "Original prompt", "is_active": True,
        "change_summary": "Rollback to v1",
    }]

    mock_agent_update = MagicMock()
    mock_agent_update.data = [{"id": "a1"}]

    with patch("app.db._db") as mock_sb:
        # get_version
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = mock_target
        # create_version -> get prev
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_prev
        # deactivate
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_deactivate
        # insert
        mock_sb.table.return_value.insert.return_value.execute.return_value = mock_insert
        # agent update (for rollback)
        mock_sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = mock_agent_update

        result = await service.rollback("v1", "u1")

    assert result is not None
    assert result["change_summary"] == "Rollback to v1"


def test_compute_diff():
    service = PromptVersionService()
    diff = service._compute_diff("Hello world", "Hello universe")
    assert "world" in diff
    assert "universe" in diff


def test_compute_diff_identical():
    service = PromptVersionService()
    diff = service._compute_diff("Same text", "Same text")
    assert diff == ""


# === API Route tests ===


def test_traces_list_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.traces.trace_service") as mock_svc:
            mock_svc.list_traces = AsyncMock(return_value=[
                {"id": "t1", "span_type": "agent_step", "span_name": "Step 1"},
            ])

            test_client = TestClient(app)
            resp = test_client.get("/api/traces")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["span_type"] == "agent_step"
    finally:
        app.dependency_overrides.clear()


def test_traces_stats_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.traces.trace_service") as mock_svc:
            mock_svc.get_trace_stats = AsyncMock(return_value={
                "total_spans": 10, "error_count": 1, "error_rate": 0.1,
                "total_tokens": 5000, "avg_latency_ms": 250.0, "by_type": {"agent_step": 10},
            })

            test_client = TestClient(app)
            resp = test_client.get("/api/traces/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_spans"] == 10
    finally:
        app.dependency_overrides.clear()


def test_trace_get_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.traces.trace_service") as mock_svc:
            mock_svc.get_trace = AsyncMock(return_value={
                "id": "t1", "span_type": "agent_step", "user_id": "user1",
            })

            test_client = TestClient(app)
            resp = test_client.get("/api/traces/t1")

        assert resp.status_code == 200
        assert resp.json()["id"] == "t1"
    finally:
        app.dependency_overrides.clear()


def test_trace_not_found():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.traces.trace_service") as mock_svc:
            mock_svc.get_trace = AsyncMock(return_value=None)

            test_client = TestClient(app)
            resp = test_client.get("/api/traces/nonexistent")

        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_prompt_versions_list_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.prompt_versions.prompt_version_service") as mock_svc:
            mock_svc.list_versions = AsyncMock(return_value=[
                {"id": "v1", "version_number": 1, "is_active": True},
            ])

            test_client = TestClient(app)
            resp = test_client.get("/api/agents/a1/prompts")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
    finally:
        app.dependency_overrides.clear()


def test_prompt_version_create_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.prompt_versions.prompt_version_service") as mock_svc:
            mock_svc.create_version = AsyncMock(return_value={
                "id": "v1", "version_number": 1, "system_prompt": "Test",
                "is_active": True, "change_summary": "Initial",
            })

            test_client = TestClient(app)
            resp = test_client.post("/api/agents/a1/prompts", json={
                "system_prompt": "Test",
                "change_summary": "Initial",
            })

        assert resp.status_code == 200
        assert resp.json()["version_number"] == 1
    finally:
        app.dependency_overrides.clear()


def test_prompt_rollback_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.prompt_versions.prompt_version_service") as mock_svc:
            mock_svc.rollback = AsyncMock(return_value={
                "id": "v3", "version_number": 3, "change_summary": "Rollback to v1",
                "is_active": True,
            })

            test_client = TestClient(app)
            resp = test_client.post("/api/prompts/v1/rollback")

        assert resp.status_code == 200
        assert "Rollback" in resp.json()["change_summary"]
    finally:
        app.dependency_overrides.clear()


def test_prompt_diff_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.prompt_versions.prompt_version_service") as mock_svc:
            mock_svc.diff_versions = AsyncMock(return_value={
                "version_a": {"id": "v1", "version_number": 1},
                "version_b": {"id": "v2", "version_number": 2},
                "diff": "--- previous\n+++ current\n-old\n+new\n",
            })

            test_client = TestClient(app)
            resp = test_client.get("/api/prompts/v1/diff/v2")

        assert resp.status_code == 200
        assert "diff" in resp.json()
    finally:
        app.dependency_overrides.clear()
