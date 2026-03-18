"""Tests for dashboard API endpoints."""

from unittest.mock import MagicMock, patch


def test_dashboard_health(client):
    response = client.get("/api/dashboard/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "dashboard"
    assert "timestamp" in data


def test_dashboard_active_requires_auth(client):
    response = client.get("/api/dashboard/active")
    assert response.status_code == 422


def test_dashboard_metrics_requires_auth(client):
    response = client.get("/api/dashboard/metrics")
    assert response.status_code == 422


def test_dashboard_timeline_requires_auth(client):
    response = client.get("/api/dashboard/timeline")
    assert response.status_code == 422


def test_dashboard_active(auth_client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.in_.return_value.order.return_value.eq.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/dashboard/active",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200
        assert response.json() == []


def test_dashboard_metrics(auth_client):
    with patch("app.db._db") as mock_db:
        mock_active = MagicMock()
        mock_active.count = 2
        mock_active.data = []
        mock_today = MagicMock()
        mock_today.count = 5
        mock_today.data = [{"tokens_used": 100, "cost_estimate": 0.01}]
        mock_agents = MagicMock()
        mock_agents.count = 3
        mock_agents.data = []

        def table_side_effect(name):
            mock_table = MagicMock()
            if name == "agent_heartbeats":
                mock_table.select.return_value.in_.return_value.eq.return_value.execute.return_value = mock_active
                mock_table.select.return_value.gte.return_value.eq.return_value.execute.return_value = mock_today
            elif name == "agents":
                mock_table.select.return_value.eq.return_value.execute.return_value = mock_agents
            return mock_table

        mock_db.table.side_effect = table_side_effect

        response = auth_client.get(
            "/api/dashboard/metrics",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "active_runs" in data
        assert "total_agents" in data
        assert "tokens_today" in data
        assert "cost_today" in data


def test_dashboard_timeline(auth_client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/dashboard/timeline",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200
        assert response.json() == []


def test_dashboard_timeline_with_events(auth_client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = [
            {
                "id": "hb1", "agent_id": "a1", "run_id": "r1", "state": "running",
                "current_step": 2, "total_steps": 5, "tokens_used": 100,
                "cost_estimate": 0.01, "output_preview": "working...",
                "updated_at": "2026-03-12T10:00:00Z",
                "agents": {"name": "TestAgent"},
            },
            {
                "id": "hb2", "agent_id": "a2", "run_id": "r2", "state": "failed",
                "current_step": 1, "total_steps": 3, "tokens_used": 50,
                "cost_estimate": 0.005, "output_preview": "error occurred",
                "updated_at": "2026-03-12T09:00:00Z",
                "agents": {"name": "FailedAgent"},
            },
            {
                "id": "hb3", "agent_id": "a3", "run_id": "r3", "state": "completed",
                "current_step": 3, "total_steps": 3, "tokens_used": 200,
                "cost_estimate": 0.02, "output_preview": "done",
                "updated_at": "2026-03-12T08:00:00Z",
                "agents": None,
            },
            {
                "id": "hb4", "agent_id": "a4", "run_id": "r4", "state": "stalled",
                "current_step": 1, "total_steps": 2, "tokens_used": 10,
                "cost_estimate": 0.001, "output_preview": "",
                "updated_at": "2026-03-12T07:00:00Z",
                "agents": {"name": "StalledAgent"},
            },
        ]
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        response = auth_client.get("/api/dashboard/timeline")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 4

        # Check severity mapping
        assert data[0]["severity"] == "info"      # running
        assert data[1]["severity"] == "error"      # failed
        assert data[2]["severity"] == "success"    # completed
        assert data[3]["severity"] == "warning"    # stalled

        # Check agent name fallback
        assert data[0]["agent_name"] == "TestAgent"
        assert data[2]["agent_name"] == "Unknown"
