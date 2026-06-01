"""PR-5 acceptance: CLI parity for the Operations kanban.

The web kanban has five lifecycle columns (Queued, Running, Awaiting Approval,
Done, Failed). The CLI mirrors them via:
  - `forge ops runs list --status <column>`
  - `forge ops approve <id>` / `forge ops reject <id>` shortcuts
"""

from unittest.mock import patch

from typer.testing import CliRunner

from forge.main import app

runner = CliRunner()


def _runs() -> list[dict]:
    return [
        {"id": "r1pendingxxxxxxxx", "agent_name": "a", "status": "pending", "tokens_used": 0, "cost": 0, "created_at": "2026-06-01T00:00:00Z"},
        {"id": "r2runningxxxxxxxx", "agent_name": "a", "status": "running", "tokens_used": 10, "cost": 0, "created_at": "2026-06-01T00:00:00Z"},
        {"id": "r3donexxxxxxxxxxx", "agent_name": "a", "status": "completed", "tokens_used": 20, "cost": 0, "created_at": "2026-06-01T00:00:00Z"},
        {"id": "r4failedxxxxxxxxx", "agent_name": "a", "status": "failed", "tokens_used": 5, "cost": 0, "created_at": "2026-06-01T00:00:00Z"},
    ]


def _invoke(args: list[str]):
    with patch("forge.client.get") as mock_get:
        mock_get.return_value = _runs()
        return runner.invoke(app, args)


def test_ops_runs_list_no_filter_shows_every_run():
    result = _invoke(["ops", "runs", "list"])
    assert result.exit_code == 0
    for prefix in ("r1pendin", "r2runnin", "r3donexx", "r4failed"):
        assert prefix in result.output


def test_ops_runs_list_status_queued_returns_pending():
    result = _invoke(["ops", "runs", "list", "--status", "queued"])
    assert result.exit_code == 0
    assert "r1pendin" in result.output
    assert "r2runnin" not in result.output
    assert "r3donexx" not in result.output
    assert "r4failed" not in result.output


def test_ops_runs_list_status_running_returns_running():
    result = _invoke(["ops", "runs", "list", "--status", "running"])
    assert result.exit_code == 0
    assert "r2runnin" in result.output
    assert "r1pendin" not in result.output


def test_ops_runs_list_status_done_returns_completed():
    result = _invoke(["ops", "runs", "list", "--status", "done"])
    assert result.exit_code == 0
    assert "r3donexx" in result.output
    assert "r2runnin" not in result.output


def test_ops_runs_list_status_failed_returns_failed():
    result = _invoke(["ops", "runs", "list", "--status", "failed"])
    assert result.exit_code == 0
    assert "r4failed" in result.output
    assert "r3donexx" not in result.output


def test_ops_runs_list_status_awaiting_approval_explains():
    result = _invoke(["ops", "runs", "list", "--status", "awaiting-approval"])
    assert result.exit_code == 0
    # Awaiting-approval items come from the approvals API, not runs — the CLI
    # explains this rather than silently returning the wrong thing.
    assert "approvals" in result.output.lower()


def test_ops_runs_list_unknown_status_errors():
    result = _invoke(["ops", "runs", "list", "--status", "bogus"])
    assert result.exit_code == 2
    assert "Unknown" in result.output


def test_ops_approve_shortcut_posts_to_backend():
    with patch("forge.client.post") as mock_post:
        result = runner.invoke(app, ["ops", "approve", "abc12345"])
        assert result.exit_code == 0
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "/api/approvals/abc12345/approve"
        assert kwargs.get("json", {}).get("feedback") == ""


def test_ops_reject_shortcut_posts_to_backend():
    with patch("forge.client.post") as mock_post:
        result = runner.invoke(app, ["ops", "reject", "abc12345", "--feedback", "no good"])
        assert result.exit_code == 0
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "/api/approvals/abc12345/reject"
        assert kwargs.get("json", {}).get("feedback") == "no good"
