"""Tests for orchestration endpoints and orchestrator service."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestOrchestrationRoutes:
    """Test orchestration API endpoints."""

    def test_list_groups(self, auth_client):
        """GET /api/orchestrate/groups returns user groups."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[
                    {"id": "g1", "objective": "Test obj", "status": "completed"},
                    {"id": "g2", "objective": "Another obj", "status": "running"},
                ]
            )
            r = auth_client.get("/api/orchestrate/groups")
            assert r.status_code == 200
            data = r.json()
            assert len(data) == 2
            assert data[0]["id"] == "g1"

    def test_list_groups_empty(self, auth_client):
        """GET /api/orchestrate/groups returns empty list when none exist."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=None
            )
            r = auth_client.get("/api/orchestrate/groups")
            assert r.status_code == 200
            assert r.json() == []

    def test_get_group_detail(self, auth_client):
        """GET /api/orchestrate/groups/{id} returns group with members."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"id": "g1", "objective": "Test", "status": "completed", "plan": []}
            )
            mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                data=[{"id": "m1", "task_description": "Do thing", "status": "completed"}]
            )
            r = auth_client.get("/api/orchestrate/groups/g1")
            assert r.status_code == 200
            data = r.json()
            assert data["id"] == "g1"
            assert len(data["members"]) == 1

    def test_get_group_not_found(self, auth_client):
        """GET /api/orchestrate/groups/{id} returns 404 when not found."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=None
            )
            r = auth_client.get("/api/orchestrate/groups/nonexistent")
            assert r.status_code == 404

    def test_get_group_result(self, auth_client):
        """GET /api/orchestrate/groups/{id}/result returns result."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"id": "g1", "status": "completed", "result": "Final answer", "objective": "Test"}
            )
            r = auth_client.get("/api/orchestrate/groups/g1/result")
            assert r.status_code == 200
            data = r.json()
            assert data["result"] == "Final answer"

    def test_get_group_result_not_found(self, auth_client):
        """GET /api/orchestrate/groups/{id}/result returns 404."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=None
            )
            r = auth_client.get("/api/orchestrate/groups/nonexistent/result")
            assert r.status_code == 404


class TestOrchestratorDecompose:
    """Test the orchestrator decompose logic."""

    @pytest.mark.asyncio
    async def test_decompose_returns_tasks(self):
        """Decompose should return a list of task dicts."""
        from app.providers.base import LLMResponse
        from app.services.orchestrator import Orchestrator

        mock_response = LLMResponse(
            content=json.dumps({
                "tasks": [
                    {"description": "Research topic", "role": "scout", "dependencies": [], "tools": ["web_search"]},
                    {"description": "Write summary", "role": "worker", "dependencies": [0], "tools": []},
                ]
            }),
            model="gpt-4o-mini",
            input_tokens=50,
            output_tokens=100,
            finish_reason="stop",
            latency_ms=200,
            provider="openai",
        )

        with patch("app.services.orchestrator.provider_registry") as mock_registry:
            mock_registry.complete = AsyncMock(return_value=mock_response)
            mock_registry.default_model = "gpt-4o-mini"

            orch = Orchestrator()
            tasks = await orch.decompose("Summarize AI trends", ["web_search"])
            assert len(tasks) == 2
            assert tasks[0]["role"] == "scout"
            assert tasks[1]["dependencies"] == [0]

    @pytest.mark.asyncio
    async def test_decompose_fallback_on_invalid_json(self):
        """Decompose should return a single fallback task on parse error."""
        from app.providers.base import LLMResponse
        from app.services.orchestrator import Orchestrator

        mock_response = LLMResponse(
            content="not valid json {{{",
            model="gpt-4o-mini",
            input_tokens=30,
            output_tokens=10,
            finish_reason="stop",
            latency_ms=100,
            provider="openai",
        )

        with patch("app.services.orchestrator.provider_registry") as mock_registry:
            mock_registry.complete = AsyncMock(return_value=mock_response)
            mock_registry.default_model = "gpt-4o-mini"

            orch = Orchestrator()
            tasks = await orch.decompose("Do something", [])
            assert len(tasks) == 1
            assert tasks[0]["description"] == "Do something"
            assert tasks[0]["role"] == "worker"
