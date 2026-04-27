"""Tests for cost API endpoints."""

from unittest.mock import MagicMock, patch


def test_cost_summary_requires_auth(client):
    response = client.get("/api/costs/summary")
    assert response.status_code == 422


def test_cost_breakdown_requires_auth(client):
    response = client.get("/api/costs/breakdown")
    assert response.status_code == 422


def test_cost_projection_requires_auth(client):
    response = client.get("/api/costs/projection")
    assert response.status_code == 422


def test_cost_summary(auth_client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = [
            {"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.0001, "model": "gpt-4o-mini"}
        ]
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/costs/summary?period=today",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_cost" in data
        assert "total_tokens" in data


def test_cost_breakdown(auth_client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/costs/breakdown?group_by=agent",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


def test_cost_breakdown_by_provider(auth_client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/costs/breakdown?group_by=provider",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200


def test_cost_projection(auth_client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/costs/projection",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "monthly_projection" in data


def test_cost_all(auth_client):
    with patch("app.db._db") as mock_db:
        mock_result = MagicMock()
        mock_result.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = mock_result
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_result

        response = auth_client.get(
            "/api/costs/all",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "today" in data
        assert "projection" in data
        assert "by_agent" in data
        assert "by_model" in data
        assert "by_provider" in data


def test_calculate_cost():
    from app.services.token_tracker import calculate_cost

    cost = calculate_cost("gpt-4o-mini", 1000, 500)
    assert cost > 0
    assert isinstance(cost, float)

    # gpt-4o should be more expensive
    cost_mini = calculate_cost("gpt-4o-mini", 1000, 1000)
    cost_4o = calculate_cost("gpt-4o", 1000, 1000)
    assert cost_4o > cost_mini
