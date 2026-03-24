"""Tests for Forge CLI commands."""

from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from forge.main import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "forge-cli" in result.output


def test_init(tmp_path):
    with patch("forge.config.CONFIG_DIR", tmp_path / ".forge"):
        with patch("forge.config.CONFIG_FILE", tmp_path / ".forge" / "config.toml"):
            result = runner.invoke(app, ["init"])
            assert result.exit_code == 0
            assert "config.toml" in result.output.lower() or "Config" in result.output


def test_status_connection_error():
    with patch("forge.client.get", side_effect=Exception("Connection refused")):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1
        assert "Error" in result.output


def test_status_no_active():
    with patch("forge.client.get") as mock_get:
        mock_get.side_effect = lambda path, **kw: {
            "/api/dashboard/active": [],
            "/api/dashboard/metrics": {
                "active_runs": 0,
                "total_agents": 3,
                "tokens_today": 0,
                "cost_today": 0.0,
            },
        }[path]

        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "No active agents" in result.output


def test_agents_list():
    with patch("forge.client.get") as mock_get:
        mock_get.return_value = [
            {
                "id": "abc12345-1234-1234-1234-123456789012",
                "name": "Test Agent",
                "tools": ["web_search"],
                "workflow_steps": ["Step 1"],
                "is_template": False,
            }
        ]

        result = runner.invoke(app, ["agents", "list"])
        assert result.exit_code == 0
        assert "Test Agent" in result.output


def test_agents_create():
    with patch("forge.client.post") as mock_post:
        mock_post.return_value = {
            "id": "new-agent-id-1234",
            "name": "My Agent",
        }

        result = runner.invoke(app, [
            "agents", "create",
            "--name", "My Agent",
            "--prompt", "You are helpful.",
        ])
        assert result.exit_code == 0
        assert "My Agent" in result.output


def test_agents_list_error():
    with patch("forge.client.get", side_effect=Exception("Unauthorized")):
        result = runner.invoke(app, ["agents", "list"])
        assert result.exit_code == 1
        assert "Error" in result.output
