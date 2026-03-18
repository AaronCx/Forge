"""Tests for heartbeat service."""

from unittest.mock import MagicMock, patch

from app.services.heartbeat import HeartbeatService


class TestHeartbeatService:
    """Test heartbeat service methods."""

    def setup_method(self):
        self.service = HeartbeatService()

    def test_start_creates_heartbeat(self):
        """start() inserts a heartbeat record and returns its ID."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
                data=[{"id": "hb-1"}]
            )
            hb_id = self.service.start("agent-1", "run-1", 5)
            assert hb_id == "hb-1"

    def test_update_partial_fields(self):
        """update() only sends provided fields."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
            self.service.update("hb-1", state="running", current_step=2)
            call_args = mock_db.table.return_value.update.call_args[0][0]
            assert call_args["state"] == "running"
            assert call_args["current_step"] == 2
            assert "tokens_used" not in call_args

    def test_update_noop_when_empty(self):
        """update() does nothing if no fields provided."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.update.reset_mock()
            self.service.update("hb-1")
            mock_db.table.return_value.update.assert_not_called()

    def test_update_truncates_preview(self):
        """update() truncates output_preview to 500 chars."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
            long_preview = "x" * 1000
            self.service.update("hb-1", output_preview=long_preview)
            call_args = mock_db.table.return_value.update.call_args[0][0]
            assert len(call_args["output_preview"]) == 500

    def test_complete_sets_state(self):
        """complete() marks heartbeat as completed."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
            self.service.complete("hb-1", tokens_used=100)
            call_args = mock_db.table.return_value.update.call_args[0][0]
            assert call_args["state"] == "completed"
            assert call_args["tokens_used"] == 100

    def test_fail_sets_state(self):
        """fail() marks heartbeat as failed."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
            self.service.fail("hb-1")
            call_args = mock_db.table.return_value.update.call_args[0][0]
            assert call_args["state"] == "failed"

    def test_get_active(self):
        """get_active() returns non-completed heartbeats."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.select.return_value.in_.return_value.order.return_value.execute.return_value = MagicMock(
                data=[{"id": "hb-1", "state": "running"}]
            )
            result = self.service.get_active()
            assert len(result) == 1
            assert result[0]["state"] == "running"

    def test_get_active_empty(self):
        """get_active() returns empty list when no active heartbeats."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.select.return_value.in_.return_value.order.return_value.execute.return_value = MagicMock(
                data=None
            )
            result = self.service.get_active()
            assert result == []

    def test_detect_stalled(self):
        """detect_stalled() finds and marks stalled heartbeats."""
        with patch("app.db._db") as mock_db:
            mock_db.table.return_value.select.return_value.in_.return_value.lt.return_value.execute.return_value = MagicMock(
                data=[{"id": "hb-stale", "state": "running"}]
            )
            mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
            result = self.service.detect_stalled()
            assert len(result) == 1
            assert result[0]["id"] == "hb-stale"

    def test_get_metrics(self):
        """get_metrics() returns aggregate stats."""
        with patch("app.db._db") as mock_db:
            # Active count
            mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(
                count=3
            )
            # Today's data
            mock_db.table.return_value.select.return_value.gte.return_value.execute.return_value = MagicMock(
                count=5, data=[{"tokens_used": 100, "cost_estimate": 0.01}]
            )
            # Total agents
            mock_db.table.return_value.select.return_value.execute.return_value = MagicMock(
                count=10
            )
            metrics = self.service.get_metrics()
            assert metrics["active_runs"] == 3
            assert metrics["total_agents"] == 10
