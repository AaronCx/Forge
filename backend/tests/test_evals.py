"""Tests for eval framework: grading methods, executor, approvals, API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.evals.approvals import ApprovalService
from app.services.evals.grading import (
    grade_contains,
    grade_custom,
    grade_exact_match,
    grade_json_schema,
)

# === Grading tests ===


def test_exact_match_pass():
    result = grade_exact_match("hello world", "hello world", {})
    assert result["passed"] is True
    assert result["score"] == 1.0


def test_exact_match_fail():
    result = grade_exact_match("hello", "world", {})
    assert result["passed"] is False
    assert result["score"] == 0.0


def test_exact_match_case_insensitive():
    result = grade_exact_match("Hello World", "hello world", {"case_sensitive": False})
    assert result["passed"] is True


def test_contains_simple():
    result = grade_contains("The quick brown fox jumps", "fox", {})
    assert result["passed"] is True
    assert result["score"] == 1.0


def test_contains_patterns():
    result = grade_contains(
        "The report contains 42 items and 3 errors",
        "",
        {"patterns": ["42", "errors"]},
    )
    assert result["passed"] is True
    assert result["matched"] == 2


def test_contains_partial_match():
    result = grade_contains(
        "Found some data",
        "",
        {"patterns": ["found", "missing"], "threshold": 0.5},
    )
    assert result["passed"] is True
    assert result["matched"] == 1


def test_contains_regex():
    result = grade_contains(
        "Error code: E-1234",
        "",
        {"patterns": [r"E-\d{4}"], "regex": True},
    )
    assert result["passed"] is True


def test_contains_fail():
    result = grade_contains("nothing here", "specific text", {})
    assert result["passed"] is False


def test_json_schema_valid():
    actual = '{"name": "test", "count": 5}'
    result = grade_json_schema(
        actual, "",
        {"schema": {"required": ["name", "count"], "properties": {"name": {"type": "string"}, "count": {"type": "integer"}}}},
    )
    assert result["passed"] is True
    assert result["score"] == 1.0


def test_json_schema_missing_key():
    actual = '{"name": "test"}'
    result = grade_json_schema(
        actual, "",
        {"schema": {"required": ["name", "count"]}},
    )
    assert result["passed"] is False
    assert "Missing required key: count" in result["errors"]


def test_json_schema_wrong_type():
    actual = '{"name": 42}'
    result = grade_json_schema(
        actual, "",
        {"schema": {"properties": {"name": {"type": "string"}}}},
    )
    assert result["passed"] is False


def test_json_schema_invalid_json():
    result = grade_json_schema("not json", "", {"schema": {}})
    assert result["passed"] is False
    assert "Invalid JSON" in result.get("error", "")


def test_json_schema_no_schema():
    result = grade_json_schema('{"any": "thing"}', "", {"schema": {}})
    assert result["passed"] is True


def test_custom_grading():
    func = """
result = {"passed": len(actual) > 5, "score": min(len(actual) / 10, 1.0)}
"""
    result = grade_custom("hello world", "", {"function": func})
    assert result["passed"] is True
    assert result["score"] > 0


def test_custom_grading_no_function():
    result = grade_custom("test", "", {})
    assert result["passed"] is False
    assert "No function" in result.get("error", "")


def test_custom_grading_error():
    result = grade_custom("test", "", {"function": "raise ValueError('boom')"})
    assert result["passed"] is False
    assert "boom" in result.get("error", "")


# === LLM Judge test (async) ===


@pytest.mark.asyncio
async def test_llm_judge():
    from app.services.evals.grading import grade_llm_judge

    mock_response = MagicMock()
    mock_response.content = '{"score": 0.85, "passed": true, "reasoning": "Good output"}'
    mock_response.input_tokens = 100
    mock_response.output_tokens = 50

    with patch("app.services.evals.grading.provider_registry") as mock_reg:
        mock_reg.complete = AsyncMock(return_value=mock_response)
        result = await grade_llm_judge("actual output", "expected output", {})

    assert result["passed"] is True
    assert result["score"] == 0.85
    assert "Good output" in result.get("reasoning", "")


# === Approval Service tests ===


@pytest.mark.asyncio
async def test_approval_create():
    service = ApprovalService()
    mock_result = MagicMock()
    mock_result.data = [{
        "id": "a1", "user_id": "u1", "blueprint_run_id": "r1",
        "node_id": "n1", "status": "pending", "context": {},
    }]

    with patch("app.services.evals.approvals.supabase") as mock_sb:
        mock_sb.table.return_value.insert.return_value.execute.return_value = mock_result
        result = await service.create_approval(
            user_id="u1", blueprint_run_id="r1", node_id="n1", context={},
        )

    assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_approval_approve():
    service = ApprovalService()

    mock_get = MagicMock()
    mock_get.data = {"id": "a1", "user_id": "u1", "status": "pending"}

    mock_update = MagicMock()
    mock_update.data = [{"id": "a1", "status": "approved", "feedback": "LGTM"}]

    with patch("app.services.evals.approvals.supabase") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_get
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_update

        result = await service.approve("a1", "u1", "LGTM")

    assert result is not None
    assert result["status"] == "approved"


@pytest.mark.asyncio
async def test_approval_reject():
    service = ApprovalService()

    mock_get = MagicMock()
    mock_get.data = {"id": "a1", "user_id": "u1", "status": "pending"}

    mock_update = MagicMock()
    mock_update.data = [{"id": "a1", "status": "rejected", "feedback": "Not ready"}]

    with patch("app.services.evals.approvals.supabase") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_get
        mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_update

        result = await service.reject("a1", "u1", "Not ready")

    assert result is not None
    assert result["status"] == "rejected"


@pytest.mark.asyncio
async def test_approval_wrong_user():
    service = ApprovalService()

    mock_get = MagicMock()
    mock_get.data = {"id": "a1", "user_id": "u1", "status": "pending"}

    with patch("app.services.evals.approvals.supabase") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_get

        result = await service.approve("a1", "u2", "")

    assert result is None


@pytest.mark.asyncio
async def test_approval_already_decided():
    service = ApprovalService()

    mock_get = MagicMock()
    mock_get.data = {"id": "a1", "user_id": "u1", "status": "approved"}

    with patch("app.services.evals.approvals.supabase") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_get

        result = await service.approve("a1", "u1", "")

    assert result is None


# === API Route tests ===


def test_approvals_list_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.approvals.approval_service") as mock_svc:
            mock_svc.list_pending = AsyncMock(return_value=[
                {"id": "a1", "status": "pending", "node_id": "n1", "blueprint_run_id": "r1"},
            ])

            test_client = TestClient(app)
            resp = test_client.get("/api/approvals")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "pending"
    finally:
        app.dependency_overrides.clear()


def test_approve_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.approvals.approval_service") as mock_svc:
            mock_svc.approve = AsyncMock(return_value={
                "id": "a1", "status": "approved", "feedback": "ok",
            })

            test_client = TestClient(app)
            resp = test_client.post("/api/approvals/a1/approve", json={"feedback": "ok"})

        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"
    finally:
        app.dependency_overrides.clear()


def test_reject_endpoint():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers.auth import get_current_user

    mock_user = MagicMock(id="user1")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.routers.approvals.approval_service") as mock_svc:
            mock_svc.reject = AsyncMock(return_value={
                "id": "a1", "status": "rejected", "feedback": "no",
            })

            test_client = TestClient(app)
            resp = test_client.post("/api/approvals/a1/reject", json={"feedback": "no"})

        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
    finally:
        app.dependency_overrides.clear()
