"""Forge CLI — main entry point.

Layout after PR-2 (unified IA):

    forge studio       …  agents, blueprints, prompts, knowledge, workspace
    forge ops          …  runs, approvals, triggers, traces, recordings, messages, groups
    forge evals        …  evals + compare
    forge connections  …  providers, mcp, targets, computer-use, tools
    forge marketplace  …  browse, publish, …
    forge settings     …  team, api-keys, config
    (system)           …  up, down, restart, status, init, version, health,
                          login, logout, whoami, dashboard

Every old top-level command name still works as an alias (`forge runs list`
keeps resolving — see `commands/aliases.py`).
"""

import typer
from rich.console import Console

from forge import __version__  # re-export
from forge.commands import (
    auth as _auth_mod,
)
from forge.commands import (
    connections as _connections_mod,
)
from forge.commands import (
    evals as _evals_mod,
)
from forge.commands import (
    marketplace as _marketplace_mod,
)
from forge.commands import (
    ops as _ops_mod,
)
from forge.commands import (
    settings as _settings_mod,
)
from forge.commands import (
    studio as _studio_mod,
)
from forge.commands import (
    system as _system_mod,
)

console = Console()

app = typer.Typer(
    name="forge",
    help="Forge CLI — manage and monitor AI agents from the terminal.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


# --- System (flat lifecycle commands) ---
# version, init, up, down, restart, status, health, dashboard, costs and the auth
# flat commands (whoami/login/logout) sit at the root. The legacy auth_app is also
# kept here so `forge auth …` continues to work.
_system_mod.register(app)
_auth_mod.register(app)


# --- The six workspace parents ---
def _workspace(name: str, help_text: str) -> typer.Typer:
    """Create a workspace parent app + register it on the root with a help panel."""
    sub = typer.Typer(help=help_text, no_args_is_help=True)
    app.add_typer(sub, name=name, rich_help_panel="Workspaces")
    return sub


# Studio / Ops / Connections / Settings are NEW grouping nouns. Each one is a fresh
# Typer parent that re-mounts the existing sub-apps under canonical names.
studio_app = _workspace("studio", "Agents, blueprints, prompts, knowledge.")
ops_app = _workspace("ops", "Runs, approvals, triggers, traces, recordings, messages.")
connections_app = _workspace(
    "connections", "Model providers, MCP, targets, computer-use config, tools."
)
settings_app = _workspace("settings", "Team, API keys, CLI config.")

studio_app.add_typer(_studio_mod.agents_app, name="agents")
studio_app.add_typer(_studio_mod.blueprints_app, name="blueprints")
studio_app.add_typer(_studio_mod.prompts_app, name="prompts")
studio_app.add_typer(_studio_mod.knowledge_app, name="knowledge")
studio_app.add_typer(_studio_mod.workspace_app, name="workspace")

ops_app.add_typer(_ops_mod.runs_app, name="runs")
ops_app.add_typer(_ops_mod.approvals_app, name="approvals")
ops_app.add_typer(_ops_mod.triggers_app, name="triggers")
ops_app.add_typer(_ops_mod.traces_app, name="traces")
ops_app.add_typer(_ops_mod.recordings_app, name="recordings")
ops_app.add_typer(_ops_mod.messages_app, name="messages")
ops_app.add_typer(_ops_mod.orchestrate_app, name="groups")  # was: orchestrate-groups
_ops_mod.register_workspace_shortcuts(ops_app)  # PR-5: forge ops approve/reject

connections_app.add_typer(
    _connections_mod.models_app, name="providers"
)  # spec rename: models → providers
connections_app.add_typer(_connections_mod.mcp_app, name="mcp")
connections_app.add_typer(_connections_mod.targets_app, name="targets")
connections_app.add_typer(_connections_mod.cu_app, name="computer-use")
connections_app.add_typer(_connections_mod.tools_app, name="tools")

settings_app.add_typer(_settings_mod.teams_app, name="team")  # spec rename: teams → team
settings_app.add_typer(_settings_mod.keys_app, name="api-keys")
settings_app.add_typer(_settings_mod.config_app, name="config")

# Evals and Marketplace keep their existing top-level names — those names ALREADY are
# the workspace. We just attach with the Workspaces help panel so they group visually
# alongside the new workspace parents.
app.add_typer(
    _evals_mod.evals_app,
    name="evals",
    rich_help_panel="Workspaces",
)
app.add_typer(
    _marketplace_mod.marketplace_app,
    name="marketplace",
    rich_help_panel="Workspaces",
)


# --- Back-compat aliases (every old top-level name keeps working) ---
# Studio / Ops / Connections / Settings modules' register() functions re-mount their
# sub-apps onto the root under the original (pre-workspace) names. So `forge runs`,
# `forge agents`, `forge models`, `forge teams`, etc. all keep resolving.
# Evals + Marketplace are skipped here: their names didn't change.
for _mod in (
    _studio_mod,
    _ops_mod,
    _connections_mod,
    _settings_mod,
):
    _mod.register(app)


def _emit_deprecation_note() -> None:
    """If the user invoked an old top-level alias, print a one-line note to stderr.

    Called from the legacy-alias callbacks below. Silenced by FORGE_NO_DEPRECATION=1
    (set in CI / scripts) so piped stdout stays clean.
    """
    import os
    import sys

    if os.environ.get("FORGE_NO_DEPRECATION") == "1":
        return
    argv = sys.argv[1:]
    if not argv:
        return
    alias = argv[0]
    new_path = _ALIAS_TO_CANONICAL.get(alias)
    if new_path is None:
        return
    sys.stderr.write(
        f"\033[2mnote: 'forge {alias}' is now 'forge {new_path}' — old form still works.\033[0m\n"
    )


# Map old top-level command → new canonical path. Used by the deprecation banner above.
# Silent aliases (no banner): "mail" (always silent — duplicate of messages).
_ALIAS_TO_CANONICAL: dict[str, str] = {
    # Studio
    "agents": "studio agents",
    "blueprints": "studio blueprints",
    "prompts": "studio prompts",
    "knowledge": "studio knowledge",
    "workspace": "studio workspace",
    # Ops
    "runs": "ops runs",
    "approvals": "ops approvals",
    "triggers": "ops triggers",
    "traces": "ops traces",
    "recordings": "ops recordings",
    "messages": "ops messages",
    "orchestrate-groups": "ops groups",
    "orchestrate": "ops orchestrate",
    "trace": "ops traces get",
    # Evals
    "compare": "evals suites compare",
    # Connections
    "models": "connections providers",
    "mcp": "connections mcp",
    "targets": "connections targets",
    "computer-use": "connections computer-use",
    "cu": "connections computer-use",
    "tools": "connections tools",
    # Settings
    "teams": "settings team",
    "keys": "settings api-keys",
    "config": "settings config",
}


# Run the deprecation hook at import-time. typer's runtime calls sys.argv early enough
# that this stderr write lands before the alias's own output (which goes to stdout).
_emit_deprecation_note()


__all__ = ["app", "console", "__version__"]


if __name__ == "__main__":
    app()
