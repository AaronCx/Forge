"""Forge CLI — auth commands (split from main.py in PR-1).

PR-1 is a mechanical refactor — zero behavior change. Each module owns a private
_app typer that captures the flat root-level commands; register(parent) forwards
them and attaches any sub-apps in this module.
"""

from pathlib import Path

import typer
from rich.console import Console

from forge import client
from forge.config import CONFIG_FILE, ensure_config, get_api_url

PIDS_FILE = Path.home() / ".forge" / "pids.json"

console = Console()

_app = typer.Typer()

auth_app = typer.Typer(help="Authentication commands")



def _save_session_token(token: str) -> None:
    """Persist a session JWT to ``[api].key`` in ``~/.forge/config.toml``.

    The previous implementation appended ``api_key = "..."`` to the end of
    the file, which TOML scopes under whichever ``[section]`` came last —
    typically ``[defaults]``. The config loader reads ``[api].key`` (or a
    top-level ``api_key`` for legacy installs), so the key was effectively
    invisible and every authenticated CLI command failed with 401/422.
    """
    ensure_config()
    lines = CONFIG_FILE.read_text().splitlines() if CONFIG_FILE.exists() else []
    in_api = False
    api_seen = False
    key_written = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_api and not key_written:
                out.append(f'key = "{token}"')
                key_written = True
            in_api = stripped == "[api]"
            if in_api:
                api_seen = True
            out.append(line)
            continue
        if in_api and stripped.startswith("key") and "=" in stripped:
            out.append(f'key = "{token}"')
            key_written = True
            continue
        out.append(line)
    if in_api and not key_written:
        out.append(f'key = "{token}"')
        key_written = True
    if not api_seen:
        out.extend(["", "[api]", f'key = "{token}"'])
    CONFIG_FILE.write_text("\n".join(out) + "\n")


@auth_app.command("signup")
def auth_signup(
    email: str = typer.Option(..., "--email", "-e", help="Email address"),
    password: str = typer.Option(..., "--password", "-p", help="Password"),
):
    """Create an account from the CLI."""
    try:
        result = client.post("/api/auth/signup", json={"email": email, "password": password})
        console.print(f"[green]Account created for {email}[/green]")
        token = result.get("access_token", "")
        if token:
            _save_session_token(token)
            console.print("[green]Session token saved to config.[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@auth_app.command("login")
def auth_login(
    email: str = typer.Option(..., "--email", "-e", help="Email address"),
    password: str = typer.Option(..., "--password", "-p", help="Password"),
):
    """Login and store session token."""
    try:
        result = client.post("/api/auth/login", json={"email": email, "password": password})
        token = result.get("access_token", "")
        if token:
            _save_session_token(token)
            console.print(f"[green]Logged in as {email}. Token saved.[/green]")
        else:
            console.print("[yellow]Login succeeded but no token returned.[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@auth_app.command("logout")
def auth_logout():
    """Clear stored session token."""
    ensure_config()
    if CONFIG_FILE.exists():
        lines = CONFIG_FILE.read_text().splitlines()
        lines = [l for l in lines if not l.strip().startswith("api_key")]
        lines.append('api_key = ""')
        CONFIG_FILE.write_text("\n".join(lines) + "\n")
    console.print("[green]Logged out. Token cleared.[/green]")


@auth_app.command("whoami")
def auth_whoami():
    """Show current user info."""
    try:
        me = client.get("/api/auth/me")
        if isinstance(me, dict):
            console.print(f"[bold]User:[/bold] {me.get('id', 'unknown')}")
            if me.get("email"):
                console.print(f"[bold]Email:[/bold] {me['email']}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@auth_app.command("keys")
def auth_keys_list_alias():
    """List API keys (alias for 'forge keys list')."""
    keys_list()

# --- Auth/utility commands ---


@_app.command()
def whoami():
    """Show current user info."""
    try:
        me = client.get("/api/auth/me")
        console.print()
        if isinstance(me, dict):
            console.print(f"[bold]User:[/bold] {me.get('id', 'unknown')}")
            console.print(f"[bold]API URL:[/bold] {get_api_url()}")
            if me.get("email"):
                console.print(f"[bold]Email:[/bold] {me['email']}")
        if isinstance(me, dict) and me.get("plan"):
            console.print(f"[bold]Plan:[/bold] {me['plan']}")
        console.print()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@_app.command()
def login(
    api_key: str = typer.Argument(..., help="API key to set"),
):
    """Set API key (alias for config set api-key)."""
    ensure_config()
    lines = []
    found = False
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            if line.strip().startswith("api_key "):
                lines.append(f'api_key = "{api_key}"')
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f'api_key = "{api_key}"')
    CONFIG_FILE.write_text("\n".join(lines) + "\n")

    masked = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
    console.print(f"[green]API key saved: {masked}[/green]")

# --- Keys commands ---


@_app.command()
def logout():
    """Clear stored credentials."""
    ensure_config()
    if CONFIG_FILE.exists():
        lines = []
        for line in CONFIG_FILE.read_text().splitlines():
            if line.strip().startswith("api_key "):
                lines.append('api_key = ""')
            else:
                lines.append(line)
        CONFIG_FILE.write_text("\n".join(lines) + "\n")
    console.print("[green]Logged out — API key cleared.[/green]")


def register(parent: typer.Typer) -> None:
    """Forward this module's flat commands and sub-apps onto the root app."""
    for cmd_info in _app.registered_commands:
        parent.registered_commands.append(cmd_info)
    parent.add_typer(auth_app, name="auth")


