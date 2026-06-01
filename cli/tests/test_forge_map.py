"""PR-6 acceptance: `forge map` prints the workspace → command tree."""

from typer.testing import CliRunner

from forge.main import app

runner = CliRunner()


def test_forge_map_lists_every_workspace():
    result = runner.invoke(app, ["map"])
    assert result.exit_code == 0
    out = result.output
    for noun in ("studio", "ops", "evals", "connections", "marketplace", "settings"):
        assert noun in out, f"{noun!r} missing from `forge map` output"


def test_forge_map_calls_out_renames():
    result = runner.invoke(app, ["map"])
    assert result.exit_code == 0
    # The map surfaces the spec renames so terminal users discover them without
    # having to read the parity doc.
    assert "providers" in result.output
    assert "team" in result.output
    assert "api-keys" in result.output


def test_forge_map_includes_pr5_shortcuts():
    result = runner.invoke(app, ["map"])
    assert result.exit_code == 0
    assert "approve" in result.output
    assert "reject" in result.output


def test_forge_map_includes_system_layer():
    result = runner.invoke(app, ["map"])
    assert result.exit_code == 0
    for cmd in ("up", "down", "status", "dashboard"):
        assert cmd in result.output
