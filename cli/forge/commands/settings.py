"""Forge CLI — settings commands (split from main.py in PR-1).

PR-1 is a mechanical refactor — zero behavior change. Each module owns a private
_app typer that captures the flat root-level commands; register(parent) forwards
them and attaches any sub-apps in this module.
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from forge import client
from forge.config import CONFIG_FILE, ensure_config, get_config

PIDS_FILE = Path.home() / ".forge" / "pids.json"

console = Console()

_app = typer.Typer()

config_app = typer.Typer(help="View and update CLI configuration")



@config_app.command("show")
def config_show():
    """Display current configuration (API key is masked)."""
    try:
        cfg = get_config()
        key = cfg.get("api_key", "")
        masked = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "***" if key else "(not set)"
        console.print()
        console.print("[bold]Forge CLI Configuration[/bold]")
        console.print(f"  api_url:       {cfg.get('api_url', '(not set)')}")
        console.print(f"  api_key:       {masked}")
        console.print(f"  default_model: {cfg.get('default_model', '(not set)')}")
        console.print(f"\n[dim]Config file: {CONFIG_FILE}[/dim]")
        console.print()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key (api-key, api-url, default-model)"),
    value: str = typer.Argument(..., help="Config value"),
):
    """Set a configuration value."""
    key_map = {
        "api-key": "api_key",
        "api-url": "api_url",
        "default-model": "default_model",
        "api_key": "api_key",
        "api_url": "api_url",
        "default_model": "default_model",
    }
    config_key = key_map.get(key)
    if not config_key:
        console.print(f"[red]Unknown config key: {key}[/red]")
        console.print("[dim]Valid keys: api-key, api-url, default-model[/dim]")
        raise typer.Exit(1)

    ensure_config()
    # Read existing config and update
    lines = []
    found = False
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            if line.strip().startswith(f"{config_key} "):
                lines.append(f'{config_key} = "{value}"')
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f'{config_key} = "{value}"')
    CONFIG_FILE.write_text("\n".join(lines) + "\n")

    display_value = f"{value[:4]}...{value[-4:]}" if config_key == "api_key" and len(value) > 8 else value
    console.print(f"[green]Set {config_key} = {display_value}[/green]")


@config_app.command("set-provider")
def config_set_provider(
    provider: str = typer.Argument(..., help="Provider name (openai, anthropic, ollama)"),
    api_key: str = typer.Argument(..., help="API key or URL"),
):
    """Configure a provider API key (also updates backend .env)."""
    # Update CLI config
    ensure_config()
    lines = CONFIG_FILE.read_text().splitlines() if CONFIG_FILE.exists() else []
    key_name = f"{provider}_api_key" if provider != "ollama" else "ollama_url"
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(key_name):
            lines[i] = f'{key_name} = "{api_key}"'
            found = True
    if not found:
        lines.append(f'{key_name} = "{api_key}"')
    CONFIG_FILE.write_text("\n".join(lines) + "\n")

    # Also update backend .env if it exists
    root = _find_project_root()
    if root:
        env_file = root / "backend" / ".env"
        if env_file.exists():
            env_key = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "google": "GOOGLE_API_KEY",
            }.get(provider)
            if env_key:
                env_lines = env_file.read_text().splitlines()
                env_found = False
                for i, line in enumerate(env_lines):
                    if line.startswith(f"{env_key}="):
                        env_lines[i] = f"{env_key}={api_key}"
                        env_found = True
                if not env_found:
                    env_lines.append(f"{env_key}={api_key}")
                env_file.write_text("\n".join(env_lines) + "\n")
                console.print(f"[green]Updated backend/.env {env_key}[/green]")

    masked = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
    console.print(f"[green]Set {provider} = {masked}[/green]")


@config_app.command("set-default-model")
def config_set_default_model(
    model: str = typer.Argument(..., help="Default model name"),
):
    """Set the default model for agent execution."""
    ensure_config()
    lines = CONFIG_FILE.read_text().splitlines() if CONFIG_FILE.exists() else []
    in_defaults = False
    found = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_defaults and not found:
                out.append(f'model = "{model}"')
                found = True
            in_defaults = stripped == "[defaults]"
            out.append(line)
            continue
        # Replace any existing model / default_model entry inside [defaults]
        if in_defaults and (stripped.startswith("model") or stripped.startswith("default_model")) and "=" in stripped:
            out.append(f'model = "{model}"')
            found = True
            continue
        out.append(line)
    if in_defaults and not found:
        out.append(f'model = "{model}"')
        found = True
    if not found:
        out.extend(["", "[defaults]", f'model = "{model}"'])
    CONFIG_FILE.write_text("\n".join(out) + "\n")
    console.print(f"[green]Default model set to: {model}[/green]")

# --- Auth commands ---


keys_app = typer.Typer(help="Manage API keys")



@keys_app.command("list")
def keys_list():
    """List API keys."""
    try:
        keys = client.get("/api/keys")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not keys:
        console.print("[dim]No API keys.[/dim]")
        return

    table = Table(title="API Keys")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Name", style="bold")
    table.add_column("Key", style="dim")
    table.add_column("Created", style="dim")

    for k in keys:
        key_val = k.get("key", k.get("prefix", ""))
        masked = f"{key_val[:8]}..." if len(key_val) > 8 else key_val
        table.add_row(
            k["id"][:8],
            k.get("name", ""),
            masked,
            k.get("created_at", "")[:10],
        )

    console.print(table)


@keys_app.command("generate")
def keys_generate(
    name: str = typer.Option(..., "--name", "-n", help="Key name"),
):
    """Generate a new API key."""
    try:
        result = client.post("/api/keys", json={"name": name})
        console.print(f"[green]Generated API key:[/green] {result.get('name', name)}")
        key_val = result.get("key", "")
        if key_val:
            console.print(f"[bold]Key: {key_val}[/bold]")
            console.print("[yellow]Save this key — it won't be shown again.[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@keys_app.command("revoke")
def keys_revoke(
    key_id: str = typer.Argument(..., help="Key ID to revoke"),
):
    """Revoke (delete) an API key."""
    typer.confirm(f"Revoke API key {key_id[:8]}?", abort=True)
    try:
        client.delete(f"/api/keys/{key_id}")
        console.print(f"[green]Revoked key {key_id[:8]}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


teams_app = typer.Typer(help="Manage organizations and teams")



@teams_app.command("list")
def teams_list():
    """List your organizations."""
    try:
        orgs = client.get("/api/organizations")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not orgs:
        console.print("[dim]No organizations.[/dim]")
        return

    table = Table(title="Organizations")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Name", style="bold")
    table.add_column("Slug")
    table.add_column("Description")

    for org in orgs:
        table.add_row(
            org["id"][:8],
            org["name"],
            f"@{org['slug']}",
            (org.get("description", "") or "")[:40],
        )

    console.print(table)


@teams_app.command("create")
def teams_create(
    name: str = typer.Option(..., "--name", "-n", help="Organization name"),
    description: str = typer.Option("", "--desc", "-d", help="Description"),
):
    """Create a new organization."""
    try:
        result = client.post("/api/organizations", json={
            "name": name,
            "description": description,
        })
        console.print(f"[green]Created:[/green] {result['name']} (@{result['slug']})")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@teams_app.command("members")
def teams_members(
    org_id: str = typer.Argument(..., help="Organization ID"),
):
    """List members of an organization."""
    try:
        members = client.get(f"/api/organizations/{org_id}/members")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not members:
        console.print("[dim]No members.[/dim]")
        return

    table = Table(title="Members")
    table.add_column("User", style="dim")
    table.add_column("Role", style="bold")
    table.add_column("Joined", style="dim")

    role_colors = {"owner": "yellow", "admin": "blue", "member": "green", "viewer": "dim"}

    for m in members:
        role = m.get("role", "member")
        color = role_colors.get(role, "white")
        table.add_row(
            m["user_id"][:12],
            f"[{color}]{role}[/{color}]",
            m.get("joined_at", "")[:10],
        )

    console.print(table)


@teams_app.command("add-member")
def teams_add_member(
    org_id: str = typer.Argument(..., help="Organization ID"),
    user_id: str = typer.Option(..., "--user", "-u", help="User ID to add"),
    role: str = typer.Option("member", "--role", "-r", help="Role: admin, member, viewer"),
):
    """Add a member to an organization."""
    try:
        client.post(f"/api/organizations/{org_id}/members", json={
            "user_id": user_id,
            "role": role,
        })
        console.print(f"[green]Added {user_id[:8]} as {role}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

# ============================================================
# Computer Use commands
# ============================================================


def register(parent: typer.Typer) -> None:
    """Forward this module's flat commands and sub-apps onto the root app."""
    for cmd_info in _app.registered_commands:
        parent.registered_commands.append(cmd_info)
    parent.add_typer(config_app, name="config")


    parent.add_typer(keys_app, name="keys")


    parent.add_typer(teams_app, name="teams")


