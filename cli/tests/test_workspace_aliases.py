"""PR-2 acceptance: the unified-IA workspace re-parent + back-compat aliases.

Every old top-level CLI noun keeps resolving to the same backend behaviour after the
introduction of the six workspace parents (studio / ops / evals / connections /
marketplace / settings).
"""

from unittest.mock import patch

from typer.testing import CliRunner

from forge.main import app

runner = CliRunner()


# --- New canonical paths resolve ---

def test_studio_agents_list_canonical():
    with patch("forge.client.get") as mock_get:
        mock_get.return_value = []
        result = runner.invoke(app, ["studio", "agents", "list"])
        assert result.exit_code == 0


def test_ops_runs_list_canonical():
    with patch("forge.client.get") as mock_get:
        mock_get.return_value = []
        result = runner.invoke(app, ["ops", "runs", "list"])
        assert result.exit_code == 0


def test_connections_providers_health_canonical():
    """connections providers is the spec rename of the former `models` sub-app."""
    with patch("forge.client.get") as mock_get:
        mock_get.return_value = []  # /api/providers/health returns a list
        result = runner.invoke(app, ["connections", "providers", "health"])
        assert result.exit_code == 0


def test_settings_team_uses_team_rename():
    """Spec rename: teams → team (matches the web's `Team` label)."""
    with patch("forge.client.get") as mock_get:
        mock_get.return_value = []
        # `forge settings team` must resolve. Just probe --help for the rename.
        result = runner.invoke(app, ["settings", "team", "--help"])
        assert result.exit_code == 0


def test_settings_api_keys_uses_api_keys_rename():
    """Spec rename: keys → api-keys under settings."""
    result = runner.invoke(app, ["settings", "api-keys", "--help"])
    assert result.exit_code == 0


def test_help_shows_workspaces_panel():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    # The six workspace nouns must appear in the Workspaces help panel.
    for noun in ("studio", "ops", "evals", "connections", "marketplace", "settings"):
        assert noun in result.output


# --- Legacy aliases continue to work ---

def test_legacy_agents_alias_resolves():
    with patch("forge.client.get") as mock_get:
        mock_get.return_value = []
        result = runner.invoke(app, ["agents", "list"])
        assert result.exit_code == 0


def test_legacy_runs_alias_resolves():
    with patch("forge.client.get") as mock_get:
        mock_get.return_value = []
        result = runner.invoke(app, ["runs", "list"])
        assert result.exit_code == 0


def test_legacy_models_alias_resolves():
    """The pre-rename `models` sub-app still resolves at the root."""
    with patch("forge.client.get") as mock_get:
        mock_get.return_value = []
        result = runner.invoke(app, ["models", "health"])
        assert result.exit_code == 0


def test_legacy_teams_alias_resolves():
    result = runner.invoke(app, ["teams", "--help"])
    assert result.exit_code == 0


def test_legacy_keys_alias_resolves():
    result = runner.invoke(app, ["keys", "--help"])
    assert result.exit_code == 0


def test_messages_and_mail_both_resolve():
    """Pre-existing dual alias (`messages` and `mail`) survives the re-parent."""
    for noun in ("messages", "mail"):
        result = runner.invoke(app, [noun, "--help"])
        assert result.exit_code == 0


def test_cu_and_computer_use_both_resolve():
    """Pre-existing dual alias (`cu` and `computer-use`) survives the re-parent."""
    for noun in ("cu", "computer-use"):
        result = runner.invoke(app, [noun, "--help"])
        assert result.exit_code == 0


# --- The deprecation note + the env-var silencer ---

def test_alias_to_canonical_map_covers_every_renamed_noun():
    """Every alias that the back-compat layer keeps alive should also map to a
    canonical workspace path, so the deprecation note can name the new home."""
    from forge.main import _ALIAS_TO_CANONICAL

    expected = {
        "agents": "studio agents",
        "blueprints": "studio blueprints",
        "prompts": "studio prompts",
        "knowledge": "studio knowledge",
        "workspace": "studio workspace",
        "runs": "ops runs",
        "approvals": "ops approvals",
        "triggers": "ops triggers",
        "traces": "ops traces",
        "recordings": "ops recordings",
        "messages": "ops messages",
        "orchestrate-groups": "ops groups",
        "orchestrate": "ops orchestrate",
        "trace": "ops traces get",
        "models": "connections providers",
        "mcp": "connections mcp",
        "targets": "connections targets",
        "computer-use": "connections computer-use",
        "cu": "connections computer-use",
        "tools": "connections tools",
        "teams": "settings team",
        "keys": "settings api-keys",
        "config": "settings config",
    }
    for alias, canonical in expected.items():
        assert _ALIAS_TO_CANONICAL.get(alias) == canonical, (
            f"alias '{alias}' should map to '{canonical}' "
            f"but got {_ALIAS_TO_CANONICAL.get(alias)!r}"
        )


def test_mail_is_silent_alias_not_in_deprecation_map():
    """Per spec: `mail` keeps working as a silent alias (no deprecation note)."""
    from forge.main import _ALIAS_TO_CANONICAL

    assert "mail" not in _ALIAS_TO_CANONICAL
