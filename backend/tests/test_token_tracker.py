"""Tests for token tracker service."""

from unittest.mock import MagicMock, patch

from app.services.token_tracker import TokenTracker, calculate_cost


class TestCalculateCost:
    """Test cost calculation."""

    def test_gpt4o_mini_cost(self):
        """Calculate cost for gpt-4o-mini."""
        cost = calculate_cost("gpt-4o-mini", 1_000_000, 1_000_000)
        assert cost == 0.75  # 0.15 + 0.60

    def test_gpt4o_cost(self):
        """Calculate cost for gpt-4o."""
        cost = calculate_cost("gpt-4o", 1_000_000, 1_000_000)
        assert cost == 12.50  # 2.50 + 10.00

    def test_unknown_model_uses_default(self):
        """Unknown model falls back to default pricing ($1.00/$3.00 per 1M)."""
        cost = calculate_cost("unknown-model", 1_000_000, 1_000_000)
        assert cost == 4.0  # 1.00 + 3.00

    def test_zero_tokens(self):
        """Zero tokens costs nothing."""
        cost = calculate_cost("gpt-4o-mini", 0, 0)
        assert cost == 0.0

    def test_small_token_count(self):
        """Small token counts produce proportional costs."""
        cost = calculate_cost("gpt-4o-mini", 1000, 1000)
        assert cost > 0
        assert cost < 0.001


class TestTokenTracker:
    """Test token tracker service methods."""

    def setup_method(self):
        self.tracker = TokenTracker()

    def test_record(self):
        """record() inserts a usage row."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
                data=[{"id": "tu-1", "cost_usd": 0.001}]
            )
            result = self.tracker.record(
                run_id="r1", agent_id="a1", user_id="u1",
                step_number=1, input_tokens=500, output_tokens=200,
            )
            assert result["id"] == "tu-1"

    def test_get_summary_today(self):
        """get_summary() aggregates today's usage."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
                data=[
                    {"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.001, "model": "gpt-4o-mini"},
                    {"input_tokens": 200, "output_tokens": 100, "cost_usd": 0.002, "model": "gpt-4o-mini"},
                ]
            )
            summary = self.tracker.get_summary("u1", "today")
            assert summary["period"] == "today"
            assert summary["total_input_tokens"] == 300
            assert summary["total_output_tokens"] == 150
            assert summary["request_count"] == 2

    def test_get_summary_empty(self):
        """get_summary() handles no data."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
                data=None
            )
            summary = self.tracker.get_summary("u1", "week")
            assert summary["total_tokens"] == 0
            assert summary["request_count"] == 0

    def test_get_run_usage(self):
        """get_run_usage() returns step-by-step usage."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                data=[{"step_number": 1, "input_tokens": 100}]
            )
            result = self.tracker.get_run_usage("r1")
            assert len(result) == 1

    def test_get_projection(self):
        """get_projection() calculates monthly estimate."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(
                data=[{"input_tokens": 1000, "output_tokens": 500, "cost_usd": 0.07, "model": "gpt-4o-mini"}]
            )
            proj = self.tracker.get_projection("u1")
            assert "daily_average" in proj
            assert "monthly_projection" in proj
            assert proj["monthly_projection"] >= 0
