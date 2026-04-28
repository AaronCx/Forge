"""Forge CLI — main entry point."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.syntax import Syntax
from rich.text import Text
from rich.tree import Tree

from forge import __version__
from forge import client
from forge.config import ensure_config, get_api_url, get_api_key, get_config, CONFIG_FILE

PIDS_FILE = Path.home() / ".forge" / "pids.json"

app = typer.Typer(
    name="forge",
    help="Forge CLI — manage and monitor AI agents from the terminal.",
    no_args_is_help=True,
)
console = Console()

agents_app = typer.Typer(help="Manage agents")
app.add_typer(agents_app, name="agents")


@app.command()
def version():
    """Show CLI version."""
    console.print(f"forge-cli v{__version__}")


@app.command()
def init():
    """Initialize CLI configuration."""
    import tomllib as _toml
    config_dir = Path.home() / ".forge"
    config_file = config_dir / "config.toml"
    if config_file.exists():
        console.print("[green]Config already exists.[/green] Run 'forge config show' to view.")
        return
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        '# Forge CLI Configuration\n\n'
        '[api]\n'
        'url = "http://localhost:8000"\n'
        'key = ""\n\n'
        '[providers]\n'
        '# Uncomment and add your keys:\n'
        '# openai_api_key = "sk-..."\n'
        '# anthropic_api_key = "sk-ant-..."\n'
        '# ollama_url = "http://localhost:11434"\n\n'
        '[defaults]\n'
        'model = "gpt-4o-mini"\n'
    )
    console.print(f"[green]Config created at {config_file}[/green] — edit to add your API keys.")


def _find_project_root() -> Path | None:
    """Walk up from cwd to find the Forge project root (has backend/ and frontend/)."""
    check = Path.cwd()
    for _ in range(10):
        if (check / "backend" / "app").is_dir() and (check / "frontend" / "package.json").is_file():
            return check
        parent = check.parent
        if parent == check:
            break
        check = parent
    return None


def _save_pids(pids: dict):
    PIDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PIDS_FILE.write_text(json.dumps(pids))


def _load_pids() -> dict:
    if PIDS_FILE.exists():
        try:
            return json.loads(PIDS_FILE.read_text())
        except Exception:
            pass
    return {}


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _wait_for_health(url: str, timeout: int = 30) -> bool:
    """Poll a URL until it returns 200 or timeout."""
    import httpx
    for _ in range(timeout):
        try:
            r = httpx.get(url, timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


@app.command()
def up():
    """Start the backend and frontend (full stack)."""
    root = _find_project_root()
    if not root:
        console.print("[red]Could not find Forge project root.[/red]")
        console.print("[dim]Run this from inside the Forge directory.[/dim]")
        raise typer.Exit(1)

    existing = _load_pids()

    # Check if already running
    if existing.get("backend") and _is_running(existing["backend"]):
        console.print("[yellow]Backend already running[/yellow] (PID {})".format(existing["backend"]))
    else:
        # Check env file
        env_file = root / "backend" / ".env"
        if not env_file.exists():
            console.print("[red]backend/.env not found.[/red] Run ./setup.sh first.")
            raise typer.Exit(1)
        env_content = env_file.read_text()
        if "your-" in env_content or "your_" in env_content:
            console.print("[yellow]Warning: backend/.env still has placeholder values — update your API keys.[/yellow]")

        # Start backend
        venv_uvicorn = root / "backend" / ".venv" / "bin" / "uvicorn"
        if not venv_uvicorn.exists():
            console.print("[red]Backend venv not found.[/red] Run ./setup.sh first.")
            raise typer.Exit(1)

        backend_proc = subprocess.Popen(
            [str(venv_uvicorn), "app.main:app", "--reload", "--port", "8000"],
            cwd=str(root / "backend"),
            stdout=open(root / "backend" / "server.log", "a"),
            stderr=subprocess.STDOUT,
        )
        existing["backend"] = backend_proc.pid
        console.print(f"[green]Backend starting[/green] (PID {backend_proc.pid})")

    if existing.get("frontend") and _is_running(existing["frontend"]):
        console.print("[yellow]Frontend already running[/yellow] (PID {})".format(existing["frontend"]))
    else:
        # Start frontend
        bun_path = "bun"
        if not any((Path(p) / "bun").exists() for p in os.environ.get("PATH", "").split(":")):
            # Try common bun location
            home_bun = Path.home() / ".bun" / "bin" / "bun"
            if home_bun.exists():
                bun_path = str(home_bun)

        frontend_proc = subprocess.Popen(
            [bun_path, "run", "dev", "--port", "3000"],
            cwd=str(root / "frontend"),
            stdout=open(root / "frontend" / "server.log", "a"),
            stderr=subprocess.STDOUT,
        )
        existing["frontend"] = frontend_proc.pid
        console.print(f"[green]Frontend starting[/green] (PID {frontend_proc.pid})")

    _save_pids(existing)

    # Wait for health
    console.print("[dim]Waiting for services...[/dim]")

    backend_ok = _wait_for_health("http://localhost:8000/health", timeout=20)
    frontend_ok = _wait_for_health("http://localhost:3000", timeout=20)

    console.print()
    if backend_ok:
        console.print("[green]✓[/green] Backend running at http://localhost:8000")
    else:
        console.print("[yellow]⚠[/yellow]  Backend not yet healthy (check backend/server.log)")
    if frontend_ok:
        console.print("[green]✓[/green] Frontend running at http://localhost:3000")
    else:
        console.print("[yellow]⚠[/yellow]  Frontend not yet healthy (check frontend/server.log)")
    if backend_ok:
        console.print("[green]✓[/green] API docs at http://localhost:8000/docs")

    console.print()
    console.print("Run [bold]forge dashboard[/bold] to monitor.")
    console.print("Run [bold]forge down[/bold] to stop everything.")


@app.command()
def down():
    """Stop the backend and frontend."""
    pids = _load_pids()
    if not pids:
        console.print("[dim]No running services found.[/dim]")
        return

    for name, pid in pids.items():
        if pid and _is_running(pid):
            try:
                os.kill(pid, signal.SIGTERM)
                console.print(f"[green]Stopped {name}[/green] (PID {pid})")
            except OSError as e:
                console.print(f"[red]Failed to stop {name} (PID {pid}): {e}[/red]")
        else:
            console.print(f"[dim]{name} not running[/dim]")

    PIDS_FILE.unlink(missing_ok=True)
    console.print("[green]All services stopped.[/green]")


@app.command()
def restart():
    """Restart backend and frontend (down + up)."""
    console.print("[bold]Stopping services...[/bold]")
    # Inline down logic
    pids = _load_pids()
    for name, pid in pids.items():
        if pid and _is_running(pid):
            try:
                os.kill(pid, signal.SIGTERM)
                console.print(f"  Stopped {name}")
            except OSError:
                pass
    PIDS_FILE.unlink(missing_ok=True)
    time.sleep(1)

    console.print("[bold]Starting services...[/bold]")
    # Delegate to up() — typer invokes it
    up()


# --- Config commands ---

config_app = typer.Typer(help="View and update CLI configuration")
app.add_typer(config_app, name="config")


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

auth_app = typer.Typer(help="Authentication commands")
app.add_typer(auth_app, name="auth")


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


@app.command()
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


@app.command()
def health():
    """Show system health status."""
    try:
        h = client.get("/health")
        dh = client.get("/api/dashboard/health")
    except Exception as e:
        console.print(f"[red]Error connecting to API: {e}[/red]")
        raise typer.Exit(1)

    status_val = h.get("status", "unknown")
    color = {"healthy": "green", "ok": "green", "degraded": "yellow", "unhealthy": "red"}.get(status_val, "white")
    console.print()
    console.print(f"[bold]System Health:[/bold] [{color}]{status_val}[/{color}]")
    console.print(f"  Version: {h.get('version', 'unknown')}")
    console.print(f"  Uptime:  {h.get('uptime', 'unknown')}")

    services = dh.get("services", {})
    if services:
        console.print("\n[bold]Services[/bold]")
        for svc, info in services.items():
            svc_status = info if isinstance(info, str) else info.get("status", "unknown")
            svc_color = {"healthy": "green", "ok": "green", "degraded": "yellow", "unhealthy": "red"}.get(svc_status, "white")
            console.print(f"  {svc}: [{svc_color}]{svc_status}[/{svc_color}]")
    console.print()


@app.command()
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

keys_app = typer.Typer(help="Manage API keys")
app.add_typer(keys_app, name="keys")


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


@app.command()
def status():
    """Show active agent runs in a table."""
    try:
        active = client.get("/api/dashboard/active")
        metrics = client.get("/api/dashboard/metrics")
    except Exception as e:
        console.print(f"[red]Error connecting to API: {e}[/red]")
        raise typer.Exit(1)

    # Metrics summary
    console.print()
    console.print(
        f"[bold]Active:[/bold] {metrics['active_runs']}  "
        f"[bold]Agents:[/bold] {metrics['total_agents']}  "
        f"[bold]Tokens today:[/bold] {metrics['tokens_today']:,}  "
        f"[bold]Cost today:[/bold] ${metrics['cost_today']:.4f}"
    )
    console.print()

    if not active:
        console.print("[dim]No active agents.[/dim]")
        return

    table = Table(title="Active Agents")
    table.add_column("Agent", style="bold")
    table.add_column("State")
    table.add_column("Progress")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost", justify="right")

    for hb in active:
        name = hb.get("agents", {}).get("name", "Unknown") if hb.get("agents") else "Unknown"
        state = hb["state"]
        state_color = {
            "running": "green",
            "starting": "yellow",
            "stalled": "red",
        }.get(state, "white")

        progress = f"{hb['current_step']}/{hb['total_steps']}"
        tokens = f"{hb['tokens_used']:,}"
        cost = f"${float(hb.get('cost_estimate', 0)):.4f}"

        table.add_row(
            name,
            f"[{state_color}]{state}[/{state_color}]",
            progress,
            tokens,
            cost,
        )

    console.print(table)


@app.command()
def dashboard(
    interval: float = typer.Option(2.0, "--interval", "-i", help="Refresh interval in seconds"),
):
    """Live-updating TUI dashboard. Press Ctrl+C to quit."""
    console.print(f"[dim]Connecting to {get_api_url()}... Press Ctrl+C to quit.[/dim]")

    def build_display() -> Panel:
        try:
            active = client.get("/api/dashboard/active")
            metrics = client.get("/api/dashboard/metrics")
            timeline = client.get("/api/dashboard/timeline", params={"limit": 10})
        except Exception as e:
            return Panel(f"[red]Error: {e}[/red]", title="Forge Dashboard")

        # Build metrics line
        metrics_text = (
            f"[bold cyan]Active:[/bold cyan] {metrics['active_runs']}  "
            f"[bold]Agents:[/bold] {metrics['total_agents']}  "
            f"[bold]Tokens:[/bold] {metrics['tokens_today']:,}  "
            f"[bold]Cost:[/bold] ${metrics['cost_today']:.4f}"
        )

        # Build agent table
        table = Table(box=None, padding=(0, 1))
        table.add_column("Agent", style="bold", min_width=20)
        table.add_column("State", min_width=10)
        table.add_column("Progress", min_width=10)
        table.add_column("Tokens", justify="right")
        table.add_column("Cost", justify="right")

        for hb in (active or []):
            name = hb.get("agents", {}).get("name", "?") if hb.get("agents") else "?"
            state = hb["state"]
            color = {"running": "green", "starting": "yellow", "stalled": "red"}.get(state, "white")
            progress = f"{hb['current_step']}/{hb['total_steps']}"
            table.add_row(
                name,
                f"[{color}]{state}[/{color}]",
                progress,
                f"{hb['tokens_used']:,}",
                f"${float(hb.get('cost_estimate', 0)):.4f}",
            )

        if not active:
            table.add_row("[dim]No active agents[/dim]", "", "", "", "")

        # Build event log
        event_lines = []
        for ev in (timeline or [])[:8]:
            sev = ev.get("severity", "info")
            color = {"error": "red", "warning": "yellow", "success": "green"}.get(sev, "blue")
            ts = ev.get("updated_at", "")[-8:] if ev.get("updated_at") else ""
            event_lines.append(f"[{color}]{ts}[/{color}] {ev.get('agent_name', '?')} — {ev.get('state', '?')}")

        events_text = "\n".join(event_lines) if event_lines else "[dim]No events[/dim]"

        layout = Layout()
        layout.split_column(
            Layout(Text.from_markup(metrics_text), size=1),
            Layout(name="spacer", size=1),
            Layout(table, name="agents"),
            Layout(name="spacer2", size=1),
            Layout(Text.from_markup(f"[bold]Events[/bold]\n{events_text}"), name="events"),
        )

        return Panel(layout, title="Forge Dashboard", subtitle="Ctrl+C to quit")

    try:
        with Live(build_display(), refresh_per_second=1, console=console) as live:
            while True:
                time.sleep(interval)
                live.update(build_display())
    except KeyboardInterrupt:
        console.print("\n[dim]Dashboard stopped.[/dim]")


# --- Agent commands ---


@agents_app.command("list")
def agents_list():
    """List all your agents."""
    try:
        agents = client.get("/api/agents")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    table = Table(title="Your Agents")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Name", style="bold")
    table.add_column("Tools")
    table.add_column("Steps", justify="right")
    table.add_column("Template")

    for agent in agents:
        table.add_row(
            agent["id"][:8],
            agent["name"],
            ", ".join(agent.get("tools", [])),
            str(len(agent.get("workflow_steps", []))),
            "Yes" if agent.get("is_template") else "",
        )

    console.print(table)


@agents_app.command("run")
def agents_run(
    agent_id: str = typer.Argument(..., help="Agent ID to run"),
    input_text: str = typer.Option("", "--input", "-i", help="Input text for the agent"),
):
    """Run an agent and stream output."""

    console.print(f"[bold]Running agent {agent_id[:8]}...[/bold]")

    try:
        for data_str in client.stream_sse(
            f"/api/agents/{agent_id}/run",
            params={"token": get_api_key(), "input_text": input_text},
        ):
            try:
                event = json.loads(data_str)
                event_type = event.get("type", "")

                if event_type == "step":
                    step_data = event.get("data", "")
                    if isinstance(step_data, dict):
                        console.print(f"[cyan]Step {step_data.get('step', '?')}[/cyan]")
                    else:
                        console.print(f"[cyan]{step_data}[/cyan]")

                elif event_type == "token":
                    token_data = event.get("data", "")
                    console.print(token_data)

                elif event_type == "done":
                    console.print(f"\n[green]Done![/green] Run ID: {event.get('run_id', 'N/A')}")

                elif event_type == "error":
                    console.print(f"[red]Error: {event.get('data', 'Unknown error')}[/red]")

            except json.JSONDecodeError:
                pass
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@agents_app.command("create")
def agents_create(
    name: str = typer.Option(..., "--name", "-n", help="Agent name"),
    prompt: str = typer.Option(..., "--prompt", "-p", help="System prompt"),
    description: str = typer.Option("", "--desc", "-d", help="Description"),
    tools: str = typer.Option("", "--tools", "-t", help="Comma-separated tool names"),
):
    """Create a new agent."""
    tool_list = [t.strip() for t in tools.split(",") if t.strip()] if tools else []

    try:
        result = client.post("/api/agents", json={
            "name": name,
            "description": description,
            "system_prompt": prompt,
            "tools": tool_list,
            "workflow_steps": [],
        })
        console.print(f"[green]Created agent:[/green] {result['name']} ({result['id'][:8]})")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@agents_app.command("show")
def agents_show(
    agent_id: str = typer.Argument(..., help="Agent ID"),
):
    """Show agent details."""
    try:
        agent = client.get(f"/api/agents/{agent_id}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    console.print()
    console.print(Panel(
        f"[bold]{agent['name']}[/bold]\n"
        f"[dim]ID: {agent['id']}[/dim]\n\n"
        f"[bold]Description:[/bold] {agent.get('description', '') or '—'}\n"
        f"[bold]Tools:[/bold] {', '.join(agent.get('tools', [])) or '—'}\n"
        f"[bold]Steps:[/bold] {len(agent.get('workflow_steps', []))}\n"
        f"[bold]Template:[/bold] {'Yes' if agent.get('is_template') else 'No'}\n"
        f"[bold]Created:[/bold] {agent.get('created_at', '')[:10]}",
        title="Agent Detail",
    ))

    if agent.get("system_prompt"):
        console.print(Panel(agent["system_prompt"][:1000], title="System Prompt", border_style="dim"))
    console.print()


@agents_app.command("edit")
def agents_edit(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    name: str = typer.Option("", "--name", "-n", help="New name"),
    prompt: str = typer.Option("", "--prompt", "-p", help="New system prompt"),
    description: str = typer.Option("", "--desc", "-d", help="New description"),
):
    """Update an agent."""
    body: dict = {}
    if name:
        body["name"] = name
    if prompt:
        body["system_prompt"] = prompt
    if description:
        body["description"] = description

    if not body:
        console.print("[red]Provide at least one of --name, --prompt, --desc[/red]")
        raise typer.Exit(1)

    try:
        result = client.put(f"/api/agents/{agent_id}", json=body)
        console.print(f"[green]Updated agent {result['id'][:8]}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@agents_app.command("delete")
def agents_delete(
    agent_id: str = typer.Argument(..., help="Agent ID to delete"),
):
    """Delete an agent."""
    typer.confirm(f"Delete agent {agent_id[:8]}?", abort=True)
    try:
        client.delete(f"/api/agents/{agent_id}")
        console.print(f"[green]Deleted agent {agent_id[:8]}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@agents_app.command("templates")
def agents_templates():
    """List agent templates."""
    try:
        templates = client.get("/api/agents/templates")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not templates:
        console.print("[dim]No agent templates.[/dim]")
        return

    table = Table(title="Agent Templates")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Tools")

    for t in templates:
        table.add_row(
            t["id"][:8],
            t["name"],
            (t.get("description", "") or "")[:50],
            ", ".join(t.get("tools", [])),
        )

    console.print(table)


@app.command()
def orchestrate(
    objective: str = typer.Argument(..., help="High-level objective to accomplish"),
    tools: str = typer.Option("", "--tools", "-t", help="Comma-separated tool names"),
):
    """Submit an objective for multi-agent orchestration."""
    tool_list = [t.strip() for t in tools.split(",") if t.strip()] if tools else []

    console.print(f"\n[bold]Objective:[/bold] {objective}")
    if tool_list:
        console.print(f"[bold]Tools:[/bold] {', '.join(tool_list)}")
    console.print()

    try:
        for data_str in client.stream_sse_post(
            "/api/orchestrate",
            json={"objective": objective, "tools": tool_list},
        ):
            try:
                event = json.loads(data_str)
                event_type = event.get("type", "")

                if event_type == "status":
                    console.print(f"[dim]{event['data']}[/dim]")

                elif event_type == "plan":
                    tasks = event["data"]
                    console.print(f"\n[bold]Task Plan ({len(tasks)} tasks)[/bold]")
                    for i, task in enumerate(tasks):
                        role = task.get("role", "worker")
                        role_color = {
                            "coordinator": "purple",
                            "supervisor": "blue",
                            "worker": "green",
                            "scout": "cyan",
                            "reviewer": "yellow",
                        }.get(role, "white")
                        deps = task.get("dependencies", [])
                        dep_str = f" [dim](depends on: {', '.join(str(d+1) for d in deps)})[/dim]" if deps else ""
                        console.print(
                            f"  {i+1}. [{role_color}][{role}][/{role_color}] "
                            f"{task.get('description', '')}{dep_str}"
                        )
                    console.print()

                elif event_type == "task_start":
                    idx = event["data"]["index"]
                    desc = event["data"].get("description", "")
                    console.print(f"  [yellow]▶ Task {idx+1}:[/yellow] {desc}")

                elif event_type == "task_done":
                    idx = event["data"]["index"]
                    preview = event["data"].get("preview", "")[:100]
                    console.print(f"  [green]✓ Task {idx+1} done[/green] — {preview}")

                elif event_type == "error":
                    console.print(f"  [red]✗ Error: {event['data']}[/red]")

                elif event_type == "result":
                    console.print("\n[bold green]Result[/bold green]")
                    console.print(Panel(event["data"], border_style="green"))
                    group_id = event.get("group_id", "")
                    if group_id:
                        console.print(f"[dim]Group ID: {group_id}[/dim]")

            except json.JSONDecodeError:
                pass
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# --- Orchestrate subcommands ---

orchestrate_app = typer.Typer(help="View orchestration groups and results")
app.add_typer(orchestrate_app, name="orchestrate-groups")


@orchestrate_app.command("status")
def orchestrate_status(
    group_id: str = typer.Argument(..., help="Task group ID"),
):
    """Show orchestration group status."""
    try:
        group = client.get(f"/api/orchestrate/groups/{group_id}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    status_val = group.get("status", "unknown")
    color = {"completed": "green", "running": "yellow", "failed": "red"}.get(status_val, "white")
    console.print()
    console.print(Panel(
        f"[bold]Group {group['id'][:8]}[/bold]\n"
        f"[bold]Status:[/bold] [{color}]{status_val}[/{color}]\n"
        f"[bold]Objective:[/bold] {group.get('objective', '—')}\n"
        f"[bold]Tasks:[/bold] {group.get('task_count', 0)}\n"
        f"[bold]Created:[/bold] {group.get('created_at', '')[:19]}",
        title="Orchestration Group",
    ))
    console.print()


@orchestrate_app.command("result")
def orchestrate_result(
    group_id: str = typer.Argument(..., help="Task group ID"),
):
    """Show orchestration group result."""
    try:
        result = client.get(f"/api/orchestrate/groups/{group_id}/result")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    output = result.get("result", result.get("output", ""))
    if isinstance(output, dict):
        console.print(Panel(json.dumps(output, indent=2), title="Result", border_style="green"))
    elif output:
        console.print(Panel(str(output)[:2000], title="Result", border_style="green"))
    else:
        console.print("[dim]No result available yet.[/dim]")


@orchestrate_app.command("history")
def orchestrate_history():
    """List past orchestration groups."""
    try:
        groups = client.get("/api/orchestrate/groups")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not groups:
        console.print("[dim]No orchestration groups.[/dim]")
        return

    table = Table(title="Orchestration History")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Objective")
    table.add_column("Status")
    table.add_column("Tasks", justify="right")
    table.add_column("Created", style="dim")

    for g in groups:
        status_val = g.get("status", "unknown")
        color = {"completed": "green", "running": "yellow", "failed": "red"}.get(status_val, "white")
        table.add_row(
            g["id"][:8],
            (g.get("objective", "") or "")[:50],
            f"[{color}]{status_val}[/{color}]",
            str(g.get("task_count", 0)),
            g.get("created_at", "")[:10],
        )

    console.print(table)


# --- Runs commands ---

runs_app = typer.Typer(help="View agent runs")
app.add_typer(runs_app, name="runs")


@runs_app.command("list")
def runs_list():
    """List agent runs."""
    try:
        runs = client.get("/api/runs")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not runs:
        console.print("[dim]No runs found.[/dim]")
        return

    table = Table(title="Agent Runs")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Agent", style="bold")
    table.add_column("Status")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Created", style="dim")

    for r in runs:
        status_val = r.get("status", "unknown")
        color = {"completed": "green", "running": "yellow", "failed": "red"}.get(status_val, "white")
        table.add_row(
            r["id"][:8],
            r.get("agent_name", r.get("agent_id", "")[:8]),
            f"[{color}]{status_val}[/{color}]",
            f"{r.get('tokens_used', 0):,}",
            f"${float(r.get('cost', 0)):.4f}",
            r.get("created_at", "")[:10],
        )

    console.print(table)


@runs_app.command("show")
def runs_show(
    run_id: str = typer.Argument(..., help="Run ID"),
):
    """Show run details."""
    try:
        run = client.get(f"/api/runs/{run_id}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    status_val = run.get("status", "unknown")
    color = {"completed": "green", "running": "yellow", "failed": "red"}.get(status_val, "white")
    console.print()
    console.print(Panel(
        f"[bold]Run {run['id'][:8]}[/bold]\n"
        f"[bold]Agent:[/bold] {run.get('agent_name', run.get('agent_id', '—'))}\n"
        f"[bold]Status:[/bold] [{color}]{status_val}[/{color}]\n"
        f"[bold]Tokens:[/bold] {run.get('tokens_used', 0):,}\n"
        f"[bold]Cost:[/bold] ${float(run.get('cost', 0)):.4f}\n"
        f"[bold]Steps:[/bold] {run.get('current_step', 0)}/{run.get('total_steps', 0)}\n"
        f"[bold]Created:[/bold] {run.get('created_at', '')[:19]}",
        title="Run Detail",
    ))

    if run.get("output"):
        output = run["output"]
        if isinstance(output, dict):
            console.print(Panel(json.dumps(output, indent=2), title="Output", border_style="green"))
        else:
            console.print(Panel(str(output)[:2000], title="Output", border_style="green"))

    if run.get("error"):
        console.print(Panel(str(run["error"]), title="Error", border_style="red"))

    console.print()


@runs_app.command("cancel")
def runs_cancel(
    run_id: str = typer.Argument(..., help="Run ID to cancel"),
):
    """Cancel an active run."""
    try:
        client.post(f"/api/runs/{run_id}/cancel")
        console.print(f"[green]Cancelled run {run_id[:8]}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


blueprints_app = typer.Typer(help="Manage blueprints")
app.add_typer(blueprints_app, name="blueprints")


@blueprints_app.command("list")
def blueprints_list():
    """List all your blueprints."""
    try:
        bps = client.get("/api/blueprints")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not bps:
        console.print("[dim]No blueprints yet.[/dim]")
        return

    table = Table(title="Your Blueprints")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Name", style="bold")
    table.add_column("Nodes", justify="right")
    table.add_column("Version", justify="right")
    table.add_column("Updated")

    for bp in bps:
        table.add_row(
            bp["id"][:8],
            bp["name"],
            str(len(bp.get("nodes", []))),
            f"v{bp.get('version', 1)}",
            bp.get("updated_at", "")[:10],
        )

    console.print(table)


@blueprints_app.command("templates")
def blueprints_templates():
    """List available blueprint templates."""
    try:
        templates = client.get("/api/blueprints/templates")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not templates:
        console.print("[dim]No templates available.[/dim]")
        return

    table = Table(title="Blueprint Templates")
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Nodes", justify="right")

    for t in templates:
        table.add_row(
            t["name"],
            t.get("description", "")[:60],
            str(len(t.get("nodes", []))),
        )

    console.print(table)


@blueprints_app.command("create")
def blueprints_create(
    name: str = typer.Option(..., "--name", "-n", help="Blueprint name"),
    description: str = typer.Option("", "--desc", "-d", help="Description"),
):
    """Create a new blueprint."""
    try:
        result = client.post("/api/blueprints", json={
            "name": name,
            "description": description,
        })
        console.print(f"[green]Created blueprint:[/green] {result['name']} ({result['id'][:8]})")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@blueprints_app.command("show")
def blueprints_show(
    blueprint_id: str = typer.Argument(..., help="Blueprint ID"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show blueprint detail."""
    try:
        bp = client.get(f"/api/blueprints/{blueprint_id}")
        if as_json:
            console.print_json(json.dumps(bp))
            return
        console.print()
        console.print(f"[bold]{bp.get('name', 'Unnamed')}[/bold]  [dim]{bp['id'][:8]}[/dim]")
        console.print(f"  Description: {bp.get('description', '-')}")
        nodes = bp.get("nodes", [])
        console.print(f"  Nodes:       {len(nodes)}")
        for n in nodes:
            ntype = n.get("type", "?")
            tag = "[blue][DET][/blue]" if ntype not in ("agent", "agent_spawn", "agent_prompt") else "[magenta][AGT][/magenta]"
            console.print(f"    {tag} {n.get('id', '?')}: {ntype}")
        edges = bp.get("edges", [])
        if edges:
            console.print(f"  Edges:       {len(edges)}")
        console.print()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@blueprints_app.command("delete")
def blueprints_delete(
    blueprint_id: str = typer.Argument(..., help="Blueprint ID to delete"),
):
    """Delete a blueprint."""
    typer.confirm(f"Delete blueprint {blueprint_id[:8]}?", abort=True)
    try:
        client.delete(f"/api/blueprints/{blueprint_id}")
        console.print(f"[green]Deleted blueprint {blueprint_id[:8]}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@blueprints_app.command("inspect")
def blueprints_inspect(
    blueprint_id: str = typer.Argument(..., help="Blueprint ID to inspect"),
):
    """Inspect a blueprint's node graph."""
    try:
        bp = client.get(f"/api/blueprints/{blueprint_id}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]{bp['name']}[/bold] (v{bp.get('version', 1)})")
    console.print(f"[dim]{bp.get('description', '')}[/dim]\n")

    nodes = bp.get("nodes", [])
    if not nodes:
        console.print("[dim]No nodes.[/dim]")
        return

    table = Table(title=f"Nodes ({len(nodes)})")
    table.add_column("ID", style="dim")
    table.add_column("Type", style="bold")
    table.add_column("Label")
    table.add_column("Class")
    table.add_column("Dependencies")

    # Determine node class from type
    agent_types = {"llm_generate", "llm_summarize", "llm_extract", "llm_review", "llm_implement"}
    for node in nodes:
        ntype = node.get("type", "")
        nclass = "agent" if ntype in agent_types else "deterministic"
        class_color = "purple" if nclass == "agent" else "blue"
        deps = ", ".join(node.get("dependencies", [])) or "—"
        table.add_row(
            node["id"],
            ntype,
            node.get("label", ""),
            f"[{class_color}]{nclass}[/{class_color}]",
            deps,
        )

    console.print(table)

    # Show execution order
    console.print(f"\n[bold]Retry policy:[/bold] max {bp.get('retry_policy', {}).get('max_retries', 0)} retries")
    if bp.get("tool_scope"):
        console.print(f"[bold]Tool scope:[/bold] {', '.join(bp['tool_scope'])}")
    console.print()


@blueprints_app.command("run")
def blueprints_run(
    blueprint_id: str = typer.Argument(..., help="Blueprint ID to run"),
    input_text: str = typer.Option("", "--input", "-i", help="Input text for the blueprint"),
):
    """Run a blueprint and stream execution progress."""
    console.print(f"[bold]Running blueprint {blueprint_id[:8]}...[/bold]\n")

    try:
        for data_str in client.stream_sse_post(
            f"/api/blueprints/{blueprint_id}/run",
            json={"input_text": input_text},
        ):
            if data_str == "[DONE]":
                break
            try:
                event = json.loads(data_str)
                event_type = event.get("type", "")

                if event_type == "status":
                    console.print(f"[dim]{event.get('data', '')}[/dim]")

                elif event_type == "layer_start":
                    layer = event.get("data", {})
                    node_ids = layer.get("node_ids", [])
                    console.print(f"[yellow]▶ Layer {layer.get('layer', '?')}:[/yellow] {', '.join(node_ids)}")

                elif event_type == "node_done":
                    d = event.get("data", {})
                    nid = d.get("node_id", "?")
                    ms = d.get("duration_ms", 0)
                    tokens = d.get("tokens", 0)
                    tok_str = f" ({tokens:,} tokens)" if tokens else ""
                    console.print(f"  [green]✓ {nid}[/green] {ms/1000:.1f}s{tok_str}")

                elif event_type == "node_error":
                    d = event.get("data", {})
                    console.print(f"  [red]✗ {d.get('node_id', '?')}: {d.get('error', 'failed')}[/red]")

                elif event_type == "result":
                    d = event.get("data", {})
                    console.print("\n[bold green]Blueprint complete[/bold green]")
                    output = d.get("output", "")
                    if isinstance(output, dict):
                        console.print(Panel(json.dumps(output, indent=2), border_style="green"))
                    elif output:
                        console.print(Panel(str(output)[:2000], border_style="green"))
                    run_id = d.get("run_id", "")
                    if run_id:
                        console.print(f"[dim]Run ID: {run_id}[/dim]")

                elif event_type == "error":
                    console.print(f"[red]Error: {event.get('data', 'Unknown error')}[/red]")

            except json.JSONDecodeError:
                pass
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@blueprints_app.command("export")
def blueprints_export(
    blueprint_id: str = typer.Argument(..., help="Blueprint ID to export"),
    output: str = typer.Option("", "--output", "-o", help="Output file path (default: stdout)"),
):
    """Export a blueprint as JSON for version control."""
    try:
        bp = client.get(f"/api/blueprints/{blueprint_id}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    export_data = {
        "name": bp["name"],
        "description": bp.get("description", ""),
        "nodes": bp.get("nodes", []),
        "edges": [],  # Derive from node dependencies
        "context_config": bp.get("context_config", {}),
        "tool_scope": bp.get("tool_scope", []),
        "retry_policy": bp.get("retry_policy", {"max_retries": 0}),
    }

    # Build edges from node dependencies
    for node in bp.get("nodes", []):
        for dep in node.get("dependencies", []):
            export_data["edges"].append({"from": dep, "to": node["id"]})

    json_str = json.dumps(export_data, indent=2)
    if output:
        Path(output).write_text(json_str)
        console.print(f"[green]Exported to {output}[/green]")
    else:
        console.print(json_str)


@blueprints_app.command("import")
def blueprints_import(
    file_path: str = typer.Argument(..., help="JSON file to import"),
):
    """Import a blueprint from a JSON definition file."""
    try:
        data = json.loads(Path(file_path).read_text())
    except FileNotFoundError:
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON: {e}[/red]")
        raise typer.Exit(1)

    try:
        bp = client.post("/api/blueprints", json=data)
        console.print(f"[green]Imported blueprint: {bp['name']} (ID: {bp['id'][:8]})[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


messages_app = typer.Typer(help="View inter-agent messages")
app.add_typer(messages_app, name="messages")
app.add_typer(messages_app, name="mail")


@messages_app.command("list")
def messages_list(
    group_id: str = typer.Argument(..., help="Task group ID"),
    message_type: str = typer.Option("", "--type", "-t", help="Filter by type: info, request, response, error, handoff"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max messages to show"),
):
    """List messages for a task group."""
    try:
        params: dict = {"limit": str(limit)}
        if message_type:
            params["message_type"] = message_type
        messages = client.get(f"/api/messages/{group_id}", params=params)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not messages:
        console.print("[dim]No messages.[/dim]")
        return

    table = Table(title=f"Messages ({len(messages)})")
    table.add_column("Type", style="bold", max_width=10)
    table.add_column("From", max_width=12)
    table.add_column("To", max_width=12)
    table.add_column("Content")
    table.add_column("Time", style="dim", max_width=10)

    type_colors = {
        "info": "blue",
        "request": "purple",
        "response": "green",
        "error": "red",
        "handoff": "yellow",
    }

    for msg in messages:
        mtype = msg.get("message_type", "info")
        color = type_colors.get(mtype, "white")
        sender = f"Agent {msg['sender_index'] + 1}"
        receiver = f"Agent {msg['receiver_index'] + 1}" if msg.get("receiver_index") is not None else "all"
        ts = msg.get("created_at", "")[-8:] if msg.get("created_at") else ""
        content = msg.get("content", "")[:80]

        table.add_row(
            f"[{color}]{mtype}[/{color}]",
            sender,
            receiver,
            content,
            ts,
        )

    console.print(table)


@messages_app.command("conversation")
def messages_conversation(
    group_id: str = typer.Argument(..., help="Task group ID"),
    agent_a: int = typer.Option(..., "--a", help="First agent index (0-based)"),
    agent_b: int = typer.Option(..., "--b", help="Second agent index (0-based)"),
):
    """View conversation between two agents."""
    try:
        messages = client.get(
            f"/api/messages/{group_id}/conversation",
            params={"agent_a": str(agent_a), "agent_b": str(agent_b)},
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not messages:
        console.print("[dim]No messages between these agents.[/dim]")
        return

    console.print(f"\n[bold]Conversation: Agent {agent_a + 1} ↔ Agent {agent_b + 1}[/bold]\n")
    for msg in messages:
        sender = f"Agent {msg['sender_index'] + 1}"
        mtype = msg.get("message_type", "info")
        content = msg.get("content", "")
        console.print(f"  [bold]{sender}[/bold] [{mtype}]: {content}")

    console.print()


@app.command()
def costs(
    breakdown: str = typer.Option("", "--breakdown", "-b", help="Breakdown by 'agent' or 'model'"),
    period: str = typer.Option("today", "--period", "-p", help="Period: today, week, month"),
):
    """Show token usage and cost summary."""
    try:
        summary = client.get("/api/costs/summary", params={"period": period})
        projection = client.get("/api/costs/projection")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    console.print()
    console.print(f"[bold]Cost Summary ({period})[/bold]")
    console.print(f"  Total cost:    [green]${summary['total_cost']:.4f}[/green]")
    console.print(f"  Input tokens:  {summary['total_input_tokens']:,}")
    console.print(f"  Output tokens: {summary['total_output_tokens']:,}")
    console.print(f"  Requests:      {summary['request_count']}")
    console.print()
    console.print("[bold]Monthly Projection[/bold]")
    console.print(f"  Daily avg:     ${projection['daily_average']:.4f}")
    console.print(f"  Monthly est:   [yellow]${projection['monthly_projection']:.2f}[/yellow]")
    console.print()

    if breakdown:
        try:
            data = client.get("/api/costs/breakdown", params={"group_by": breakdown})
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)

        table = Table(title=f"Breakdown by {breakdown}")
        table.add_column("Name", style="bold")
        table.add_column("Cost", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Requests", justify="right")

        for entry in data:
            table.add_row(
                entry["name"],
                f"${entry['cost']:.4f}",
                f"{entry['input_tokens'] + entry['output_tokens']:,}",
                str(entry["requests"]),
            )

        console.print(table)


models_app = typer.Typer(help="Manage models and providers")
app.add_typer(models_app, name="models")


@models_app.command("list")
def models_list(
    provider: str = typer.Option("", "--provider", "-p", help="Filter by provider"),
):
    """List available models across all providers."""
    try:
        if provider:
            models = client.get(f"/api/providers/models/{provider}")
        else:
            models = client.get("/api/providers/models")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not models:
        console.print("[dim]No models available.[/dim]")
        return

    table = Table(title="Available Models")
    table.add_column("Model ID", style="bold")
    table.add_column("Provider")
    table.add_column("Context", justify="right")
    table.add_column("Max Output", justify="right")
    table.add_column("Tools")
    table.add_column("Stream")

    for m in models:
        ctx = f"{m['context_window']:,}" if m.get("context_window") else "—"
        out = f"{m['max_output_tokens']:,}" if m.get("max_output_tokens") else "—"
        table.add_row(
            m["id"],
            m["provider"],
            ctx,
            out,
            "Yes" if m.get("supports_tools", True) else "No",
            "Yes" if m.get("supports_streaming", True) else "No",
        )

    console.print(table)


@models_app.command("health")
def models_health():
    """Check health of all configured providers."""
    try:
        health = client.get("/api/providers/health")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    table = Table(title="Provider Health")
    table.add_column("Provider", style="bold")
    table.add_column("Status")
    table.add_column("Latency", justify="right")
    table.add_column("Error")

    status_colors = {
        "healthy": "green",
        "degraded": "yellow",
        "unavailable": "red",
    }

    for h in health:
        color = status_colors.get(h["status"], "white")
        latency = f"{h['latency_ms']:.0f}ms" if h.get("latency_ms") else "—"
        table.add_row(
            h["provider"],
            f"[{color}]{h['status']}[/{color}]",
            latency,
            h.get("error", "") or "",
        )

    console.print(table)


@models_app.command("test")
def models_test(
    model: str = typer.Argument(..., help="Model ID to test"),
    prompt: str = typer.Option("Say hello in one sentence.", "--prompt", "-p", help="Test prompt"),
):
    """Send a test prompt to a specific model."""
    console.print(f"[dim]Testing {model}...[/dim]")
    try:
        result = client.post("/api/compare", json={
            "prompt": prompt,
            "models": [model],
        })
        results = result.get("results", [])
        if results:
            r = results[0]
            if r.get("error"):
                console.print(f"[red]Error: {r['error']}[/red]")
            else:
                console.print(f"\n[bold]{r['model']}[/bold] ({r['provider']})")
                console.print(r["content"])
                console.print(f"\n[dim]Tokens: {r['input_tokens']+r['output_tokens']} | "
                              f"Latency: {r['latency_ms']/1000:.1f}s | "
                              f"Cost: ${r['cost']:.4f}[/dim]")
        else:
            console.print("[red]No results returned.[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# --- MCP commands ---

mcp_app = typer.Typer(help="Manage MCP server connections")
app.add_typer(mcp_app, name="mcp")


@mcp_app.command("connect")
def mcp_connect(
    name: str = typer.Option(..., "--name", "-n", help="Connection name"),
    url: str = typer.Option(..., "--url", "-u", help="MCP server URL"),
):
    """Connect to an MCP server."""
    try:
        result = client.post("/api/mcp/connect", json={
            "name": name,
            "server_url": url,
        })
        tools = result.get("tools_discovered", [])
        console.print(f"[green]Connected to {result['name']}[/green]")
        console.print(f"  Status: {result['status']}")
        console.print(f"  Tools discovered: {len(tools)}")
        for t in tools[:10]:
            console.print(f"    - {t['name']}: {t.get('description', '')[:60]}")
        if len(tools) > 10:
            console.print(f"    ... and {len(tools) - 10} more")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@mcp_app.command("list")
def mcp_list():
    """List MCP server connections."""
    try:
        connections = client.get("/api/mcp/connections")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not connections:
        console.print("[dim]No MCP connections.[/dim]")
        return

    table = Table(title="MCP Connections")
    table.add_column("Name", style="bold")
    table.add_column("URL")
    table.add_column("Status")
    table.add_column("Tools", justify="right")

    status_colors = {"connected": "green", "disconnected": "yellow", "error": "red"}

    for conn in connections:
        status = conn.get("status", "unknown")
        color = status_colors.get(status, "white")
        tools_count = len(conn.get("tools_discovered", []))
        table.add_row(
            conn["name"],
            conn["server_url"],
            f"[{color}]{status}[/{color}]",
            str(tools_count),
        )

    console.print(table)


@mcp_app.command("test")
def mcp_test(
    connection_id: str = typer.Argument(..., help="Connection ID to test"),
):
    """Test an MCP server connection."""
    try:
        result = client.post(f"/api/mcp/connections/{connection_id}/test", json={})
        status = result.get("status", "unknown")
        color = {"connected": "green", "disconnected": "yellow", "error": "red"}.get(status, "white")
        console.print(f"Status: [{color}]{status}[/{color}]")
        if result.get("latency_ms"):
            console.print(f"Latency: {result['latency_ms']:.0f}ms")
        if result.get("error"):
            console.print(f"[red]Error: {result['error']}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@mcp_app.command("tools")
def mcp_tools():
    """List all available tools (built-in + MCP)."""
    try:
        tools = client.get("/api/tools")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not tools:
        console.print("[dim]No tools available.[/dim]")
        return

    table = Table(title="Available Tools")
    table.add_column("Name", style="bold")
    table.add_column("Source")
    table.add_column("Description")

    for t in tools:
        source = t.get("source", "built-in")
        source_style = "blue" if source == "built-in" else "purple"
        table.add_row(
            t["name"],
            f"[{source_style}]{source}[/{source_style}]",
            t.get("description", "")[:60],
        )

    console.print(table)


# --- Trigger commands ---

triggers_app = typer.Typer(help="Manage event triggers")
app.add_typer(triggers_app, name="triggers")


@triggers_app.command("list")
def triggers_list():
    """List all triggers."""
    try:
        triggers = client.get("/api/triggers")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not triggers:
        console.print("[dim]No triggers configured.[/dim]")
        return

    table = Table(title="Triggers")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Type", style="bold")
    table.add_column("Target")
    table.add_column("Enabled")
    table.add_column("Fired", justify="right")

    for t in triggers:
        enabled_str = "[green]Yes[/green]" if t.get("enabled") else "[red]No[/red]"
        target = f"{t['target_type']}:{t['target_id'][:8]}"
        table.add_row(
            t["id"][:8],
            t["type"],
            target,
            enabled_str,
            str(t.get("fire_count", 0)),
        )

    console.print(table)


@triggers_app.command("create")
def triggers_create(
    trigger_type: str = typer.Option(..., "--type", "-t", help="Trigger type: webhook, cron, mcp_event"),
    target_type: str = typer.Option(..., "--target-type", help="Target type: agent or blueprint"),
    target_id: str = typer.Option(..., "--target-id", help="Target agent/blueprint ID"),
    cron: str = typer.Option("", "--cron", "-c", help="Cron expression (for cron triggers)"),
):
    """Create a new trigger."""
    config: dict = {}
    if trigger_type == "cron" and cron:
        config["cron_expression"] = cron

    try:
        result = client.post("/api/triggers", json={
            "type": trigger_type,
            "config": config,
            "target_type": target_type,
            "target_id": target_id,
        })
        console.print(f"[green]Created trigger:[/green] {result['id'][:8]} ({trigger_type})")
        if trigger_type == "webhook":
            from forge.config import get_api_url
            console.print(f"  Webhook URL: {get_api_url()}/api/webhooks/{result['id']}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@triggers_app.command("toggle")
def triggers_toggle(
    trigger_id: str = typer.Argument(..., help="Trigger ID to toggle"),
):
    """Toggle a trigger on/off."""
    try:
        result = client.put(f"/api/triggers/{trigger_id}/toggle", json={})
        state = "enabled" if result.get("enabled") else "disabled"
        console.print(f"[green]Trigger {trigger_id[:8]} is now {state}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@triggers_app.command("edit")
def triggers_edit(
    trigger_id: str = typer.Argument(..., help="Trigger ID to update"),
    config: str = typer.Option("", "--config", "-c", help="JSON config string"),
    enabled: bool = typer.Option(None, "--enabled/--disabled", help="Enable or disable"),
):
    """Update a trigger."""
    body: dict = {}
    if config:
        body["config"] = json.loads(config)
    if enabled is not None:
        body["enabled"] = enabled

    if not body:
        console.print("[red]Provide at least one of --config, --enabled/--disabled[/red]")
        raise typer.Exit(1)

    try:
        result = client.put(f"/api/triggers/{trigger_id}", json=body)
        console.print(f"[green]Updated trigger {result['id'][:8]}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@triggers_app.command("delete")
def triggers_delete(
    trigger_id: str = typer.Argument(..., help="Trigger ID to delete"),
):
    """Delete a trigger."""
    typer.confirm(f"Delete trigger {trigger_id[:8]}?", abort=True)
    try:
        client.delete(f"/api/triggers/{trigger_id}")
        console.print(f"[green]Deleted trigger {trigger_id[:8]}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@triggers_app.command("history")
def triggers_history(
    trigger_id: str = typer.Argument(..., help="Trigger ID"),
):
    """Show trigger firing history."""
    try:
        history = client.get(f"/api/triggers/{trigger_id}/history")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not history:
        console.print("[dim]No firing history.[/dim]")
        return

    table = Table(title=f"Trigger {trigger_id[:8]} History")
    table.add_column("Fired At", style="dim")
    table.add_column("Status")
    table.add_column("Run ID", style="dim", max_width=8)
    table.add_column("Detail")

    for h in history:
        status_val = h.get("status", "unknown")
        color = {"success": "green", "failed": "red", "skipped": "yellow"}.get(status_val, "white")
        table.add_row(
            h.get("fired_at", "")[:19],
            f"[{color}]{status_val}[/{color}]",
            (h.get("run_id", "") or "")[:8],
            (h.get("detail", "") or "")[:50],
        )

    console.print(table)


# --- Eval commands ---

evals_app = typer.Typer(help="Manage eval suites and runs")
app.add_typer(evals_app, name="evals")


@evals_app.command("list")
def evals_list():
    """List eval suites."""
    try:
        suites = client.get("/api/evals/suites")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not suites:
        console.print("[dim]No eval suites.[/dim]")
        return

    table = Table(title="Eval Suites")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Name", style="bold")
    table.add_column("Target")
    table.add_column("Cases", justify="right")

    for s in suites:
        table.add_row(
            s["id"][:8],
            s["name"],
            f"{s['target_type']}:{s['target_id'][:8]}",
            str(len(s.get("cases", []))),
        )

    console.print(table)


@evals_app.command("run")
def evals_run(
    suite_id: str = typer.Argument(..., help="Eval suite ID"),
    model: str = typer.Option("", "--model", "-m", help="Override model for this run"),
):
    """Run an eval suite."""
    console.print(f"[bold]Running eval suite {suite_id[:8]}...[/bold]")
    try:
        body: dict = {}
        if model:
            body["model"] = model
        result = client.post(f"/api/evals/suites/{suite_id}/run", json=body)
        console.print("[green]Eval complete![/green]")
        console.print(f"  Pass rate: {result.get('pass_rate', 0) * 100:.0f}%")
        console.print(f"  Avg score: {result.get('avg_score', 0):.2f}")
        console.print(f"  Passed: {result.get('passed_cases', 0)}/{result.get('total_cases', 0)}")
        console.print(f"  Run ID: {result.get('run_id', '')[:8]}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@evals_app.command("compare")
def evals_compare(
    run_a: str = typer.Argument(..., help="First run ID"),
    run_b: str = typer.Argument(..., help="Second run ID"),
):
    """Compare two eval runs to see regressions."""
    try:
        result = client.get(f"/api/evals/runs/{run_a}/compare/{run_b}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    a_info = result.get("run_a", {})
    b_info = result.get("run_b", {})
    console.print(f"\n[bold]Run A[/bold] ({a_info.get('id', '')[:8]}): "
                  f"pass_rate={a_info.get('pass_rate', 0) * 100:.0f}%")
    console.print(f"[bold]Run B[/bold] ({b_info.get('id', '')[:8]}): "
                  f"pass_rate={b_info.get('pass_rate', 0) * 100:.0f}%")
    console.print(f"\n  Regressions: [red]{result.get('regressions', 0)}[/red]")
    console.print(f"  Improvements: [green]{result.get('improvements', 0)}[/green]")

    comparisons = result.get("comparisons", [])
    if comparisons:
        table = Table(title="Case Comparison")
        table.add_column("Case", style="dim", max_width=8)
        table.add_column("Status")
        table.add_column("Score A", justify="right")
        table.add_column("Score B", justify="right")
        table.add_column("Diff", justify="right")

        for c in comparisons:
            status = c.get("status", "")
            color = {"regression": "red", "improvement": "green", "unchanged": "dim"}.get(status, "white")
            score_a = f"{c.get('run_a_score', 0):.2f}" if c.get("run_a_score") is not None else "—"
            score_b = f"{c.get('run_b_score', 0):.2f}" if c.get("run_b_score") is not None else "—"
            diff = f"{c.get('score_diff', 0):+.2f}" if c.get("score_diff") else "—"
            table.add_row(c["case_id"][:8], f"[{color}]{status}[/{color}]", score_a, score_b, diff)

        console.print(table)


@evals_app.command("create")
def evals_create(
    name: str = typer.Option(..., "--name", "-n", help="Suite name"),
    target_type: str = typer.Option(..., "--target-type", "-t", help="Target type: agent or blueprint"),
    target_id: str = typer.Option(..., "--target-id", help="Target agent/blueprint ID"),
):
    """Create a new eval suite."""
    try:
        result = client.post("/api/evals/suites", json={
            "name": name,
            "target_type": target_type,
            "target_id": target_id,
        })
        console.print(f"[green]Created eval suite:[/green] {result['name']} ({result['id'][:8]})")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@evals_app.command("add-case")
def evals_add_case(
    suite_id: str = typer.Argument(..., help="Suite ID"),
    name: str = typer.Option(..., "--name", "-n", help="Test case name"),
    input_text: str = typer.Option(..., "--input", "-i", help="Input text"),
    expected: str = typer.Option(..., "--expected", "-e", help="Expected output"),
):
    """Add a test case to an eval suite."""
    try:
        result = client.post(f"/api/evals/suites/{suite_id}/cases", json={
            "name": name,
            "input": input_text,
            "expected_output": expected,
        })
        console.print(f"[green]Added case:[/green] {result.get('name', name)} ({result['id'][:8]})")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# --- Approval commands ---

approvals_app = typer.Typer(help="Manage human-in-the-loop approvals")
app.add_typer(approvals_app, name="approvals")


@approvals_app.command("list")
def approvals_list(
    show_all: bool = typer.Option(False, "--all", "-a", help="Show all approvals, not just pending"),
):
    """List pending approvals."""
    try:
        status = "all" if show_all else "pending"
        approvals = client.get(f"/api/approvals?status={status}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not approvals:
        console.print("[dim]No pending approvals.[/dim]")
        return

    table = Table(title="Approvals")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Status")
    table.add_column("Node")
    table.add_column("Run", style="dim", max_width=8)
    table.add_column("Created")

    status_colors = {"pending": "yellow", "approved": "green", "rejected": "red"}

    for a in approvals:
        color = status_colors.get(a["status"], "white")
        table.add_row(
            a["id"][:8],
            f"[{color}]{a['status']}[/{color}]",
            a.get("node_id", ""),
            a["blueprint_run_id"][:8],
            a.get("created_at", "")[:10],
        )

    console.print(table)


@approvals_app.command("approve")
def approvals_approve(
    approval_id: str = typer.Argument(..., help="Approval ID"),
    feedback: str = typer.Option("", "--feedback", "-f", help="Optional feedback"),
):
    """Approve a pending checkpoint."""
    try:
        client.post(f"/api/approvals/{approval_id}/approve", json={"feedback": feedback})
        console.print(f"[green]Approved {approval_id[:8]}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@approvals_app.command("reject")
def approvals_reject(
    approval_id: str = typer.Argument(..., help="Approval ID"),
    feedback: str = typer.Option("", "--feedback", "-f", help="Rejection reason"),
):
    """Reject a pending checkpoint."""
    try:
        client.post(f"/api/approvals/{approval_id}/reject", json={"feedback": feedback})
        console.print(f"[red]Rejected {approval_id[:8]}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# --- Trace commands ---

traces_app = typer.Typer(help="View execution traces")
app.add_typer(traces_app, name="traces")


@traces_app.command("list")
def traces_list(
    run_id: str = typer.Option("", "--run", "-r", help="Filter by run ID"),
    agent_id: str = typer.Option("", "--agent", "-a", help="Filter by agent ID"),
    span_type: str = typer.Option("", "--type", "-t", help="Filter by span type"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max traces to show"),
):
    """List recent execution traces."""
    try:
        params: dict = {"limit": str(limit)}
        if run_id:
            params["run_id"] = run_id
        if agent_id:
            params["agent_id"] = agent_id
        if span_type:
            params["span_type"] = span_type
        traces = client.get("/api/traces", params=params)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not traces:
        console.print("[dim]No traces found.[/dim]")
        return

    table = Table(title="Traces")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Type", style="bold")
    table.add_column("Name")
    table.add_column("Model", style="dim")
    table.add_column("Status")
    table.add_column("Tokens", justify="right")
    table.add_column("Latency", justify="right")
    table.add_column("Time", style="dim", max_width=10)

    status_colors = {"ok": "green", "running": "yellow", "error": "red", "timeout": "red"}

    for t in traces:
        status = t.get("status", "ok")
        color = status_colors.get(status, "white")
        tokens = t.get("input_tokens", 0) + t.get("output_tokens", 0)
        latency = t.get("latency_ms", 0)
        ts = t.get("created_at", "")[-8:] if t.get("created_at") else ""
        table.add_row(
            t["id"][:8],
            t.get("span_type", ""),
            (t.get("span_name", "") or "")[:40],
            t.get("model", "") or "",
            f"[{color}]{status}[/{color}]",
            f"{tokens:,}" if tokens else "",
            f"{latency:.0f}ms" if latency else "",
            ts,
        )

    console.print(table)


@traces_app.command("stats")
def traces_stats():
    """Show trace statistics for today."""
    try:
        stats = client.get("/api/traces/stats")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    console.print()
    console.print("[bold]Trace Stats (today)[/bold]")
    console.print(f"  Total spans:  {stats['total_spans']}")
    console.print(f"  Errors:       [red]{stats['error_count']}[/red] ({stats['error_rate'] * 100:.1f}%)")
    console.print(f"  Total tokens: {stats['total_tokens']:,}")
    console.print(f"  Avg latency:  {stats['avg_latency_ms']:.0f}ms")

    by_type = stats.get("by_type", {})
    if by_type:
        console.print("\n[bold]By type:[/bold]")
        for span_type, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
            console.print(f"  {span_type}: {count}")
    console.print()


@traces_app.command("get")
def traces_get(
    trace_id: str = typer.Argument(..., help="Trace ID to inspect"),
):
    """Inspect a trace and its child spans."""
    try:
        tree = client.get(f"/api/traces/{trace_id}/tree")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not tree:
        console.print("[red]Trace not found.[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]{tree.get('span_name', 'Unnamed')}[/bold]")
    console.print(f"  Type:    {tree.get('span_type', '')}")
    console.print(f"  Status:  {tree.get('status', '')}")
    console.print(f"  Model:   {tree.get('model', '') or '—'}")
    tokens = tree.get("input_tokens", 0) + tree.get("output_tokens", 0)
    console.print(f"  Tokens:  {tokens:,}")
    console.print(f"  Latency: {tree.get('latency_ms', 0):.0f}ms")

    if tree.get("input_preview"):
        console.print("\n[bold]Input:[/bold]")
        console.print(Panel(tree["input_preview"][:500], border_style="dim"))

    if tree.get("output_preview"):
        console.print("\n[bold]Output:[/bold]")
        console.print(Panel(tree["output_preview"][:500], border_style="green"))

    if tree.get("error_message"):
        console.print("\n[bold red]Error:[/bold red]")
        console.print(Panel(tree["error_message"], border_style="red"))

    children = tree.get("children", [])
    if children:
        console.print(f"\n[bold]Child Spans ({len(children)})[/bold]")
        for child in children:
            status = child.get("status", "ok")
            color = {"ok": "green", "error": "red"}.get(status, "white")
            ctokens = child.get("input_tokens", 0) + child.get("output_tokens", 0)
            console.print(
                f"  [{color}]{status}[/{color}] {child.get('span_type', '')} — "
                f"{child.get('span_name', '')[:50]} "
                f"[dim]({ctokens:,} tok, {child.get('latency_ms', 0):.0f}ms)[/dim]"
            )

    console.print()


# --- Prompt version commands ---

prompts_app = typer.Typer(help="Manage prompt versions")
app.add_typer(prompts_app, name="prompts")


@prompts_app.command("list")
def prompts_list(
    agent_id: str = typer.Argument(..., help="Agent ID"),
):
    """List prompt versions for an agent."""
    try:
        versions = client.get(f"/api/agents/{agent_id}/prompts")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not versions:
        console.print("[dim]No prompt versions for this agent.[/dim]")
        return

    table = Table(title="Prompt Versions")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Version", style="bold", justify="right")
    table.add_column("Summary")
    table.add_column("Active")
    table.add_column("Created", style="dim")

    for v in versions:
        active = "[green]Yes[/green]" if v.get("is_active") else ""
        table.add_row(
            v["id"][:8],
            f"v{v['version_number']}",
            v.get("change_summary", "")[:50],
            active,
            v.get("created_at", "")[:10],
        )

    console.print(table)


@prompts_app.command("snapshot")
def prompts_snapshot(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    summary: str = typer.Option("Manual snapshot", "--summary", "-s", help="Change summary"),
):
    """Snapshot the current prompt as a new version."""
    try:
        # Get agent's current prompt
        agent = client.get(f"/api/agents/{agent_id}")
        result = client.post(f"/api/agents/{agent_id}/prompts", json={
            "system_prompt": agent["system_prompt"],
            "change_summary": summary,
        })
        console.print(f"[green]Created v{result['version_number']}[/green]: {result.get('change_summary', '')}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@prompts_app.command("rollback")
def prompts_rollback(
    version_id: str = typer.Argument(..., help="Version ID to rollback to"),
):
    """Rollback to a specific prompt version."""
    try:
        result = client.post(f"/api/prompts/{version_id}/rollback", json={})
        console.print(f"[green]Rolled back — created v{result['version_number']}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@prompts_app.command("diff")
def prompts_diff(
    version_a: str = typer.Argument(..., help="First version ID"),
    version_b: str = typer.Argument(..., help="Second version ID"),
):
    """Compare two prompt versions."""
    try:
        result = client.get(f"/api/prompts/{version_a}/diff/{version_b}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    a = result.get("version_a", {})
    b = result.get("version_b", {})
    console.print(f"\n[bold]v{a.get('version_number', '?')} → v{b.get('version_number', '?')}[/bold]\n")

    diff_text = result.get("diff", "")
    if not diff_text:
        console.print("[dim]No differences.[/dim]")
    else:
        for line in diff_text.split("\n"):
            if line.startswith("+"):
                console.print(f"[green]{line}[/green]")
            elif line.startswith("-"):
                console.print(f"[red]{line}[/red]")
            elif line.startswith("@@"):
                console.print(f"[blue]{line}[/blue]")
            else:
                console.print(line)

    console.print()


# --- Knowledge commands ---

knowledge_app = typer.Typer(help="Manage knowledge base collections")
app.add_typer(knowledge_app, name="knowledge")


@knowledge_app.command("list")
def knowledge_list():
    """List knowledge collections."""
    try:
        collections = client.get("/api/knowledge/collections")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not collections:
        console.print("[dim]No knowledge collections.[/dim]")
        return

    table = Table(title="Knowledge Collections")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Name", style="bold")
    table.add_column("Docs", justify="right")
    table.add_column("Chunks", justify="right")
    table.add_column("Model", style="dim")

    for c in collections:
        table.add_row(
            c["id"][:8],
            c["name"],
            str(c.get("document_count", 0)),
            str(c.get("chunk_count", 0)),
            c.get("embedding_model", ""),
        )

    console.print(table)


@knowledge_app.command("create")
def knowledge_create(
    name: str = typer.Option(..., "--name", "-n", help="Collection name"),
    description: str = typer.Option("", "--desc", "-d", help="Description"),
):
    """Create a new knowledge collection."""
    try:
        result = client.post("/api/knowledge/collections", json={
            "name": name,
            "description": description,
        })
        console.print(f"[green]Created collection:[/green] {result['name']} ({result['id'][:8]})")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@knowledge_app.command("add")
def knowledge_add(
    collection_id: str = typer.Argument(..., help="Collection ID"),
    filename: str = typer.Option(..., "--file", "-f", help="Filename label"),
    text: str = typer.Option("", "--text", "-t", help="Raw text (or use --stdin)"),
    stdin: bool = typer.Option(False, "--stdin", help="Read text from stdin"),
):
    """Add a document to a collection."""
    import sys
    if stdin:
        text = sys.stdin.read()
    if not text:
        console.print("[red]Provide text with --text or --stdin[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Adding {filename} ({len(text)} chars)...[/dim]")
    try:
        result = client.post(f"/api/knowledge/collections/{collection_id}/documents", json={
            "filename": filename,
            "raw_text": text,
        })
        console.print(f"[green]Added {result.get('filename', filename)}[/green] — "
                      f"status: {result.get('status', '?')}, chunks: {result.get('chunk_count', 0)}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@knowledge_app.command("search")
def knowledge_search(
    collection_id: str = typer.Argument(..., help="Collection ID"),
    query: str = typer.Argument(..., help="Search query"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results"),
):
    """Search a knowledge collection."""
    console.print("[dim]Searching...[/dim]")
    try:
        results = client.post(f"/api/knowledge/collections/{collection_id}/search", json={
            "query": query,
            "top_k": top_k,
        })
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    for i, r in enumerate(results, 1):
        sim = r.get("similarity", 0) * 100
        content = r.get("content", "")[:200]
        console.print(f"\n[bold]#{i}[/bold] ({sim:.1f}% match)")
        console.print(Panel(content, border_style="dim"))


@knowledge_app.command("delete")
def knowledge_delete(
    collection_id: str = typer.Argument(..., help="Collection ID to delete"),
):
    """Delete a knowledge collection."""
    typer.confirm(f"Delete collection {collection_id[:8]}?", abort=True)
    try:
        client.delete(f"/api/knowledge/collections/{collection_id}")
        console.print(f"[green]Deleted collection {collection_id[:8]}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@knowledge_app.command("documents")
def knowledge_documents(
    collection_id: str = typer.Argument(..., help="Collection ID"),
):
    """List documents in a collection."""
    try:
        docs = client.get(f"/api/knowledge/collections/{collection_id}/documents")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not docs:
        console.print("[dim]No documents in this collection.[/dim]")
        return

    table = Table(title="Documents")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Filename", style="bold")
    table.add_column("Chunks", justify="right")
    table.add_column("Status")
    table.add_column("Added", style="dim")

    for d in docs:
        status_val = d.get("status", "unknown")
        color = {"ready": "green", "processing": "yellow", "error": "red"}.get(status_val, "white")
        table.add_row(
            d["id"][:8],
            d.get("filename", ""),
            str(d.get("chunk_count", 0)),
            f"[{color}]{status_val}[/{color}]",
            d.get("created_at", "")[:10],
        )

    console.print(table)


@knowledge_app.command("remove-doc")
def knowledge_remove_doc(
    document_id: str = typer.Argument(..., help="Document ID to remove"),
):
    """Remove a document from its collection."""
    typer.confirm(f"Remove document {document_id[:8]}?", abort=True)
    try:
        client.delete(f"/api/knowledge/documents/{document_id}")
        console.print(f"[green]Removed document {document_id[:8]}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# --- Marketplace commands ---

marketplace_app = typer.Typer(help="Browse and publish to the marketplace")
app.add_typer(marketplace_app, name="marketplace")


@marketplace_app.command("browse")
def marketplace_browse(
    category: str = typer.Option("", "--category", "-c", help="Filter by category"),
    search_query: str = typer.Option("", "--search", "-s", help="Search by title"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
):
    """Browse marketplace listings."""
    try:
        params: dict = {"limit": str(limit)}
        if category:
            params["category"] = category
        if search_query:
            params["search"] = search_query
        listings = client.get("/api/marketplace/listings", params=params)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not listings:
        console.print("[dim]No listings found.[/dim]")
        return

    table = Table(title="Marketplace")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Title", style="bold")
    table.add_column("Category")
    table.add_column("Rating", justify="right")
    table.add_column("Forks", justify="right")
    table.add_column("Version", style="dim")

    for li in listings:
        rating = f"{li.get('rating_avg', 0):.1f} ({li.get('rating_count', 0)})"
        table.add_row(
            li["id"][:8],
            li["title"],
            li.get("category", ""),
            rating,
            str(li.get("fork_count", 0)),
            li.get("version", ""),
        )

    console.print(table)


@marketplace_app.command("publish")
def marketplace_publish(
    blueprint_id: str = typer.Option(..., "--blueprint", "-b", help="Blueprint ID to publish"),
    title: str = typer.Option(..., "--title", "-t", help="Listing title"),
    description: str = typer.Option("", "--desc", "-d", help="Description"),
    category: str = typer.Option("general", "--category", "-c", help="Category"),
):
    """Publish a blueprint to the marketplace."""
    try:
        result = client.post("/api/marketplace/listings", json={
            "blueprint_id": blueprint_id,
            "title": title,
            "description": description,
            "category": category,
        })
        console.print(f"[green]Published:[/green] {result['title']} ({result['id'][:8]})")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@marketplace_app.command("rate")
def marketplace_rate(
    listing_id: str = typer.Argument(..., help="Listing ID to rate"),
    rating: int = typer.Option(..., "--rating", "-r", help="Rating 1-5"),
    review: str = typer.Option("", "--review", help="Optional review text"),
):
    """Rate a marketplace listing."""
    if rating < 1 or rating > 5:
        console.print("[red]Rating must be 1-5[/red]")
        raise typer.Exit(1)
    try:
        client.post(f"/api/marketplace/listings/{listing_id}/rate", json={
            "rating": rating,
            "review": review,
        })
        console.print(f"[green]Rated {listing_id[:8]} with {rating}/5[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@marketplace_app.command("fork")
def marketplace_fork(
    listing_id: str = typer.Argument(..., help="Listing ID to fork"),
    blueprint_id: str = typer.Option(..., "--blueprint", "-b", help="New blueprint ID for the fork"),
):
    """Fork a marketplace listing."""
    try:
        result = client.post(f"/api/marketplace/listings/{listing_id}/fork", json={
            "forked_blueprint_id": blueprint_id,
        })
        console.print(f"[green]Forked {listing_id[:8]}[/green] → {result.get('forked_blueprint_id', blueprint_id)[:8]}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@marketplace_app.command("show")
def marketplace_show(
    listing_id: str = typer.Argument(..., help="Listing ID"),
):
    """Show marketplace listing details."""
    try:
        li = client.get(f"/api/marketplace/listings/{listing_id}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    rating = f"{li.get('rating_avg', 0):.1f}/5 ({li.get('rating_count', 0)} ratings)"
    console.print()
    console.print(Panel(
        f"[bold]{li['title']}[/bold]\n"
        f"[dim]ID: {li['id']}[/dim]\n\n"
        f"[bold]Category:[/bold] {li.get('category', '—')}\n"
        f"[bold]Version:[/bold] {li.get('version', '—')}\n"
        f"[bold]Rating:[/bold] {rating}\n"
        f"[bold]Forks:[/bold] {li.get('fork_count', 0)}\n"
        f"[bold]Description:[/bold] {li.get('description', '') or '—'}",
        title="Marketplace Listing",
    ))
    console.print()


@marketplace_app.command("unpublish")
def marketplace_unpublish(
    listing_id: str = typer.Argument(..., help="Listing ID to unpublish"),
):
    """Unpublish a marketplace listing."""
    typer.confirm(f"Unpublish listing {listing_id[:8]}?", abort=True)
    try:
        client.delete(f"/api/marketplace/listings/{listing_id}")
        console.print(f"[green]Unpublished listing {listing_id[:8]}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# --- Team/Org commands ---

teams_app = typer.Typer(help="Manage organizations and teams")
app.add_typer(teams_app, name="teams")


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

cu_app = typer.Typer(help="Computer use — GUI and terminal automation")
app.add_typer(cu_app, name="computer-use")
app.add_typer(cu_app, name="cu")


@cu_app.command("status")
def cu_status():
    """Show computer use capability status."""
    try:
        report = client.get("/api/computer-use/status")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    ready = report.get("computer_use_ready", False)
    console.print()
    console.print(
        f"[{'green' if ready else 'yellow'}]Computer Use: "
        f"{'Ready' if ready else 'Not Ready'}[/{'green' if ready else 'yellow'}]"
    )
    console.print()

    table = Table(title="Components")
    table.add_column("Component")
    table.add_column("Status")
    table.add_column("Version")

    for name, avail_key, ver_key in [
        ("Steer (GUI)", "steer_available", "steer_version"),
        ("Drive (Terminal)", "drive_available", "drive_version"),
        ("tmux", "tmux_available", "tmux_version"),
    ]:
        available = report.get(avail_key, False)
        version = report.get(ver_key, "")
        status = "[green]Installed[/green]" if available else "[red]Missing[/red]"
        table.add_row(name, status, version)

    table.add_row(
        "macOS",
        f"[green]{report.get('macos_version', 'Yes')}[/green]" if report.get("is_macos") else "[red]Not macOS[/red]",
        report.get("macos_version", ""),
    )

    console.print(table)

    missing = report.get("missing", [])
    if missing:
        console.print()
        console.print("[yellow]Install instructions:[/yellow]")
        for component, instruction in report.get("install_instructions", {}).items():
            console.print(f"\n[bold]{component}:[/bold]")
            console.print(f"  {instruction}")


@cu_app.command("see")
def cu_see(
    app_name: str = typer.Option("screen", "--app", "-a", help="App to screenshot"),
):
    """Take a screenshot."""
    try:
        result = client.post("/api/blueprints/node-exec", json={
            "node_type": "steer_see",
            "config": {"target": app_name},
        })
        path = result.get("screenshot_path", "")
        console.print(f"[green]Screenshot saved: {path}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@cu_app.command("ocr")
def cu_ocr(
    app_name: str = typer.Option("screen", "--app", "-a", help="App to read"),
):
    """Run OCR and display detected text."""
    try:
        result = client.post("/api/blueprints/node-exec", json={
            "node_type": "steer_ocr",
            "config": {"target": app_name},
        })
        text = result.get("text", "")
        count = result.get("element_count", 0)
        console.print(f"[dim]({count} elements detected)[/dim]")
        console.print(text)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@cu_app.command("click")
def cu_click(
    x: int = typer.Argument(..., help="X coordinate"),
    y: int = typer.Argument(..., help="Y coordinate"),
):
    """Click at coordinates."""
    try:
        client.post("/api/blueprints/node-exec", json={
            "node_type": "steer_click",
            "config": {"x": x, "y": y},
        })
        console.print(f"[green]Clicked at ({x}, {y})[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@cu_app.command("type")
def cu_type(
    text: str = typer.Argument(..., help="Text to type"),
):
    """Type text into the focused app."""
    try:
        client.post("/api/blueprints/node-exec", json={
            "node_type": "steer_type",
            "config": {"text": text},
        })
        console.print(f"[green]Typed {len(text)} characters[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@cu_app.command("hotkey")
def cu_hotkey(
    keys: str = typer.Argument(..., help="Key combination (e.g. cmd+s)"),
):
    """Send a keyboard shortcut."""
    try:
        client.post("/api/blueprints/node-exec", json={
            "node_type": "steer_hotkey",
            "config": {"keys": keys},
        })
        console.print(f"[green]Sent hotkey: {keys}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@cu_app.command("run")
def cu_run(
    command: str = typer.Argument(..., help="Command to execute"),
    session: str = typer.Option("", "--session", "-s", help="tmux session name"),
):
    """Run a terminal command via Drive."""
    try:
        result = client.post("/api/blueprints/node-exec", json={
            "node_type": "drive_run",
            "config": {"command": command, "session": session},
        })
        console.print(result.get("text", ""))
        exit_code = result.get("exit_code", 0)
        if exit_code != 0:
            console.print(f"[yellow]Exit code: {exit_code}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@cu_app.command("logs")
def cu_logs(
    session: str = typer.Option("", "--session", "-s", help="tmux session name"),
    lines: int = typer.Option(100, "--lines", "-n", help="Number of lines"),
):
    """Capture terminal output from a tmux pane."""
    try:
        result = client.post("/api/blueprints/node-exec", json={
            "node_type": "drive_logs",
            "config": {"session": session, "lines": lines},
        })
        console.print(result.get("text", ""))
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@cu_app.command("sessions")
def cu_sessions():
    """List active tmux sessions."""
    try:
        result = client.post("/api/blueprints/node-exec", json={
            "node_type": "drive_session",
            "config": {"action": "list"},
        })
        sessions = result.get("sessions", [])
        if not sessions:
            console.print("[dim]No active sessions.[/dim]")
            return
        for s in sessions:
            console.print(f"  {s}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@cu_app.command("apps")
def cu_apps():
    """List running macOS applications."""
    try:
        result = client.post("/api/blueprints/node-exec", json={
            "node_type": "steer_apps",
            "config": {},
        })
        apps = result.get("apps", [])
        if not apps:
            console.print("[dim]No apps detected.[/dim]")
            return
        for app_info in apps:
            name = app_info.get("name", str(app_info)) if isinstance(app_info, dict) else str(app_info)
            console.print(f"  {name}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@cu_app.command("remote")
def cu_remote_test():
    """Test connection to the remote Listen server."""
    try:
        result = client.post("/api/computer-use/remote/test")
        if result.get("connected"):
            console.print(f"[green]Connected to {result.get('server_url')}[/green]")
        else:
            console.print(f"[red]Not connected: {result.get('error', 'Unknown error')}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# ─── Agent Backends (agent-on-agent orchestration) ───

backends_app = typer.Typer(help="Manage agent backends (Claude Code, Codex, Gemini CLI, Aider)")
cu_app.add_typer(backends_app, name="backends")


@backends_app.command("list")
def backends_list():
    """List configured agent backends."""
    try:
        result = client.get("/api/computer-use/status")
        backends = result.get("agent_backends", [])
        table = Table(title="Agent Backends")
        table.add_column("Name", style="cyan")
        table.add_column("Available", style="green")

        known = ["claude-code", "codex-cli", "gemini-cli", "aider"]
        for name in known:
            avail = "✓" if name in backends else "✗"
            style = "green" if name in backends else "red"
            table.add_row(name, f"[{style}]{avail}[/{style}]")

        console.print(table)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@backends_app.command("test")
def backends_test(name: str = typer.Argument(..., help="Backend name to test")):
    """Verify a backend CLI is installed and working."""
    import shutil
    from forge import client as _  # noqa

    backend_commands = {
        "claude-code": "claude",
        "codex-cli": "codex",
        "gemini-cli": "gemini",
        "aider": "aider",
    }
    cmd = backend_commands.get(name, name)
    path = shutil.which(cmd)
    if path:
        console.print(f"[green]✓ {name} found at {path}[/green]")
    else:
        console.print(f"[red]✗ {name} ({cmd}) not found in PATH[/red]")
        raise typer.Exit(1)


# ─── Execution Targets (multi-machine dispatch) ───

targets_app = typer.Typer(help="Manage execution targets for multi-machine dispatch")
app.add_typer(targets_app, name="targets")


@targets_app.command("list")
def targets_list():
    """Show all execution targets with health status."""
    try:
        result = client.get("/api/targets")
        table = Table(title="Execution Targets")
        table.add_column("ID", style="dim")
        table.add_column("Name", style="cyan")
        table.add_column("Type")
        table.add_column("Platform")
        table.add_column("Status")
        table.add_column("URL")

        for t in result:
            status_style = "green" if t["status"] == "healthy" else "red" if t["status"] == "unhealthy" else "yellow"
            table.add_row(
                t["id"][:8],
                t["name"],
                t["type"],
                t.get("platform", ""),
                f"[{status_style}]{t['status']}[/{status_style}]",
                t.get("listen_url", "") or "local",
            )

        console.print(table)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@targets_app.command("add")
def targets_add(
    name: str = typer.Option(..., "--name", help="Target name"),
    url: str = typer.Option(..., "--url", help="Listen server URL"),
    api_key: str = typer.Option("", "--api-key", help="API key"),
    platform: str = typer.Option("macos", "--platform", help="Platform (macos/linux/windows)"),
):
    """Register a new execution target."""
    try:
        result = client.post("/api/targets", json={
            "name": name,
            "target_type": "remote",
            "listen_url": url,
            "api_key": api_key,
            "platform": platform,
        })
        console.print(f"[green]✓ Added target: {result.get('name')} (ID: {result.get('id', '')[:8]})[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@targets_app.command("health")
def targets_health():
    """Run health checks on all targets."""
    try:
        targets = client.get("/api/targets")
        for t in targets:
            result = client.post(f"/api/targets/{t['id']}/health")
            status = result.get("status", "unknown")
            style = "green" if status == "healthy" else "red"
            console.print(f"  [{style}]{t['name']}: {status}[/{style}]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@targets_app.command("remove")
def targets_remove(target_id: str = typer.Argument(..., help="Target ID")):
    """Remove an execution target."""
    try:
        result = client.delete(f"/api/targets/{target_id}")
        if result.get("removed"):
            console.print(f"[green]✓ Removed target {target_id}[/green]")
        else:
            console.print(f"[red]Failed: {result.get('error', 'unknown')}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# ─── Screen Recordings ───

recordings_app = typer.Typer(help="Manage screen recordings of agent sessions")
app.add_typer(recordings_app, name="recordings")


@recordings_app.command("list")
def recordings_list():
    """List available recordings."""
    import os
    storage = os.getenv("AF_RECORDING_STORAGE", "/tmp/forge-recordings")
    if not os.path.exists(storage):
        console.print("[yellow]No recordings directory found.[/yellow]")
        return

    files = sorted(os.listdir(storage), reverse=True)
    if not files:
        console.print("[yellow]No recordings found.[/yellow]")
        return

    table = Table(title="Screen Recordings")
    table.add_column("File", style="cyan")
    table.add_column("Size")
    table.add_column("Modified")

    for f in files[:20]:
        path = os.path.join(storage, f)
        size = os.path.getsize(path)
        mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
        table.add_row(f, f"{size / 1024 / 1024:.1f} MB", mtime)

    console.print(table)


@recordings_app.command("play")
def recordings_play(run_id: str = typer.Argument(..., help="Run ID")):
    """Open a recording in the system video player."""
    import os
    import subprocess
    storage = os.getenv("AF_RECORDING_STORAGE", "/tmp/forge-recordings")
    for f in os.listdir(storage) if os.path.exists(storage) else []:
        if run_id in f:
            path = os.path.join(storage, f)
            subprocess.run(["open", path])
            console.print(f"[green]Opening {f}[/green]")
            return
    console.print(f"[red]No recording found for run {run_id}[/red]")


@recordings_app.command("cleanup")
def recordings_cleanup(older_than: int = typer.Option(30, "--older-than", help="Days")):
    """Delete recordings older than N days."""
    import os
    storage = os.getenv("AF_RECORDING_STORAGE", "/tmp/forge-recordings")
    if not os.path.exists(storage):
        console.print("[yellow]No recordings directory.[/yellow]")
        return

    cutoff = time.time() - (older_than * 86400)
    removed = 0
    for f in os.listdir(storage):
        path = os.path.join(storage, f)
        if os.path.getmtime(path) < cutoff:
            os.remove(path)
            removed += 1
    console.print(f"[green]Removed {removed} recordings older than {older_than} days.[/green]")


@recordings_app.command("download")
def recordings_download(
    run_id: str = typer.Argument(..., help="Run ID of the recording"),
    output: str = typer.Option("", "--output", "-o", help="Output file path"),
):
    """Download a recording to a local file."""
    import os
    import shutil

    storage = os.getenv("AF_RECORDING_STORAGE", "/tmp/forge-recordings")
    source = None
    if os.path.exists(storage):
        for f in os.listdir(storage):
            if run_id in f:
                source = os.path.join(storage, f)
                break

    if not source:
        console.print(f"[red]No recording found for run {run_id}[/red]")
        raise typer.Exit(1)

    dest = output if output else os.path.basename(source)
    shutil.copy2(source, dest)
    size = os.path.getsize(dest) / 1024 / 1024
    console.print(f"[green]Downloaded to {dest} ({size:.1f} MB)[/green]")


@app.command()
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


tools_app = typer.Typer(help="List available tools (built-in and MCP)")
app.add_typer(tools_app, name="tools")


@tools_app.command("list")
def tools_list():
    """List all available tools (built-in + MCP)."""
    try:
        data = client.get("/api/tools")
        tools = data if isinstance(data, list) else data.get("tools", [])
        table = Table(title="Available Tools")
        table.add_column("Name", style="cyan")
        table.add_column("Source")
        table.add_column("Description", max_width=50)
        for t in tools:
            source = t.get("source", t.get("server_name", "built-in"))
            table.add_row(t.get("name", "?"), source, t.get("description", ""))
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def compare(
    prompt: str = typer.Argument(..., help="Prompt to compare across models"),
    models: str = typer.Option(..., "--models", "-m", help="Comma-separated model names"),
    system_prompt: str = typer.Option("", "--system", "-s", help="System prompt"),
):
    """Compare responses across multiple models."""
    model_list = [m.strip() for m in models.split(",")]
    try:
        result = client.post("/api/compare", json={
            "prompt": prompt,
            "models": model_list,
            "system_prompt": system_prompt,
        })
        table = Table(title="Model Comparison")
        table.add_column("Model", style="cyan")
        table.add_column("Latency")
        table.add_column("Tokens")
        table.add_column("Cost")
        table.add_column("Response", max_width=60)
        for r in result.get("results", []):
            table.add_row(
                r.get("model", "?"),
                f"{r.get('latency_ms', 0)}ms",
                str(r.get("total_tokens", "?")),
                f"${r.get('cost', 0):.4f}",
                (r.get("response", "")[:60] + "...") if len(r.get("response", "")) > 60 else r.get("response", ""),
            )
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def trace(
    run_id: str = typer.Argument(..., help="Run ID to trace"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full event data"),
):
    """Show execution trace for a run (alias for traces get)."""
    try:
        data = client.get(f"/api/traces/{run_id}")
        spans = data.get("spans", [data] if "span_type" in data else [])
        if not spans:
            console.print("[yellow]No trace data found.[/yellow]")
            return
        console.print(f"\n[bold]Trace for run {run_id[:8]}[/bold]\n")
        type_colors = {
            "agent_step": "magenta", "llm_call": "cyan", "tool_call": "green",
            "node_execution": "blue", "blueprint_step": "yellow",
        }
        for s in spans:
            stype = s.get("span_type", "?")
            color = type_colors.get(stype, "white")
            status = s.get("status", "?")
            status_icon = {"completed": "[green]✓[/green]", "error": "[red]✗[/red]", "running": "[blue]●[/blue]"}.get(status, status)
            duration = f" ({s.get('duration_ms', '?')}ms)" if s.get("duration_ms") else ""
            tokens = f" [{s.get('total_tokens', '')} tok]" if s.get("total_tokens") else ""
            console.print(f"  {status_icon} [{color}]{stype}[/{color}] {s.get('name', '')}{duration}{tokens}")
            if verbose:
                if s.get("input"):
                    console.print(f"      [dim]Input:[/dim] {str(s['input'])[:200]}")
                if s.get("output"):
                    console.print(f"      [dim]Output:[/dim] {str(s['output'])[:200]}")
                if s.get("error"):
                    console.print(f"      [red]Error: {s['error']}[/red]")
        console.print()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# --- Missing commands from spec (Fix 3) ---


@evals_app.command("results")
def evals_results(
    run_id: str = typer.Argument(..., help="Eval run ID"),
):
    """Show results for an eval run."""
    try:
        run = client.get(f"/api/evals/runs/{run_id}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]Eval Run {run['id'][:8]}[/bold]")
    console.print(f"  Status: {run.get('status', '?')}")
    console.print(f"  Pass rate: {(run.get('pass_rate', 0) or 0) * 100:.0f}%")
    console.print(f"  Cases: {run.get('passed_cases', 0)}/{run.get('total_cases', 0)}")

    results = run.get("results", [])
    if results:
        table = Table(title="Results")
        table.add_column("Case", style="dim", max_width=8)
        table.add_column("Passed")
        table.add_column("Score", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Latency", justify="right")

        for r in results:
            passed = r.get("passed")
            p_str = "[green]✓[/green]" if passed else "[red]✗[/red]" if passed is not None else "—"
            score = f"{r.get('score', 0):.2f}" if r.get("score") is not None else "—"
            table.add_row(
                r.get("case_id", "")[:8],
                p_str,
                score,
                str(r.get("tokens_used", 0)),
                f"{r.get('latency_ms', 0)}ms" if r.get("latency_ms") else "—",
            )
        console.print(table)
    console.print()


@approvals_app.command("show")
def approvals_show(
    approval_id: str = typer.Argument(..., help="Approval ID"),
):
    """Show approval detail with context."""
    try:
        a = client.get(f"/api/approvals/{approval_id}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    status_val = a.get("status", "unknown")
    color = {"pending": "yellow", "approved": "green", "rejected": "red"}.get(status_val, "white")
    console.print(f"\n[bold]Approval {a['id'][:8]}[/bold]")
    console.print(f"  Status: [{color}]{status_val}[/{color}]")
    console.print(f"  Node: {a.get('node_id', '—')}")
    console.print(f"  Blueprint Run: {a.get('blueprint_run_id', '—')[:8]}")
    if a.get("context"):
        console.print(Panel(json.dumps(a["context"], indent=2), title="Context"))
    if a.get("feedback"):
        console.print(f"  Feedback: {a['feedback']}")
    console.print()


@mcp_app.command("remove")
def mcp_remove(
    connection_id: str = typer.Argument(..., help="Connection ID to remove"),
):
    """Remove an MCP connection."""
    typer.confirm(f"Remove MCP connection {connection_id[:8]}?", abort=True)
    try:
        client.delete(f"/api/mcp/connections/{connection_id}")
        console.print(f"[green]Removed MCP connection {connection_id[:8]}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@triggers_app.command("fire")
def triggers_fire(
    trigger_id: str = typer.Argument(..., help="Trigger ID to fire"),
    input_text: str = typer.Option("", "--input", "-i", help="Input text"),
):
    """Manually fire a trigger (for testing)."""
    try:
        result = client.post(f"/api/triggers/{trigger_id}/fire", json={"input": input_text})
        console.print(f"[green]Trigger fired.[/green]")
        if result.get("run_id"):
            console.print(f"  Run ID: {result['run_id'][:8]}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@marketplace_app.command("search")
def marketplace_search(
    query: str = typer.Argument(..., help="Search query"),
):
    """Search the marketplace."""
    try:
        results = client.get("/api/marketplace/listings", params={"search": query})
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not results:
        console.print("[dim]No results.[/dim]")
        return

    table = Table(title=f'Marketplace: "{query}"')
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Title", style="bold")
    table.add_column("Category")
    table.add_column("Rating", justify="right")
    table.add_column("Forks", justify="right")

    for item in results:
        table.add_row(
            item["id"][:8],
            item["title"],
            item.get("category", "—"),
            f"{'★' * int(item.get('rating_avg', 0))}" if item.get("rating_avg") else "—",
            str(item.get("fork_count", 0)),
        )
    console.print(table)


@agents_app.command("history")
def agents_history(
    agent_id: str = typer.Argument(..., help="Agent ID"),
):
    """Show run history for an agent."""
    try:
        runs = client.get(f"/api/runs", params={"agent_id": agent_id, "limit": "20"})
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not runs:
        console.print("[dim]No runs for this agent.[/dim]")
        return

    table = Table(title="Run History")
    table.add_column("Run ID", style="dim", max_width=8)
    table.add_column("Status")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Created")

    for r in runs:
        status = r.get("status", "?")
        color = {"completed": "green", "running": "yellow", "failed": "red"}.get(status, "white")
        dur = f"{r.get('duration_ms', 0)}ms" if r.get("duration_ms") else "—"
        table.add_row(
            r["id"][:8],
            f"[{color}]{status}[/{color}]",
            f"{r.get('tokens_used', 0):,}",
            f"${float(r.get('cost', 0)):.4f}",
            dur,
            r.get("created_at", "")[:16],
        )
    console.print(table)


@cu_app.command("scroll")
def cu_scroll(
    direction: str = typer.Argument(..., help="Direction: up, down, left, right"),
    amount: int = typer.Argument(3, help="Scroll amount (lines)"),
    app_name: str = typer.Option("", "--app", help="Target app"),
):
    """Scroll in a direction."""
    try:
        result = client.post("/api/computer-use/execute", json={
            "command": "scroll", "args": {"direction": direction, "amount": amount, "app": app_name}
        })
        console.print(f"[green]Scrolled {direction} {amount}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@cu_app.command("focus")
def cu_focus(
    app_name: str = typer.Argument(..., help="App name to focus"),
):
    """Focus an application."""
    try:
        result = client.post("/api/computer-use/execute", json={
            "command": "focus", "args": {"app": app_name}
        })
        console.print(f"[green]Focused {app_name}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@cu_app.command("find")
def cu_find(
    text: str = typer.Argument(..., help="Text to find on screen"),
):
    """Find an element on screen by text (OCR match)."""
    try:
        result = client.post("/api/computer-use/execute", json={
            "command": "find", "args": {"text": text}
        })
        if isinstance(result, dict):
            matches = result.get("matches", [])
            if matches:
                for m in matches:
                    console.print(f"  Found at ({m.get('x', '?')}, {m.get('y', '?')}): {m.get('text', '')}")
            else:
                console.print("[dim]No matches found.[/dim]")
        else:
            console.print(str(result))
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@cu_app.command("drag")
def cu_drag(
    x1: int = typer.Argument(..., help="Start X"),
    y1: int = typer.Argument(..., help="Start Y"),
    x2: int = typer.Argument(..., help="End X"),
    y2: int = typer.Argument(..., help="End Y"),
):
    """Drag from one point to another."""
    try:
        client.post("/api/computer-use/execute", json={
            "command": "drag", "args": {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        })
        console.print(f"[green]Dragged ({x1},{y1}) → ({x2},{y2})[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@backends_app.command("add")
def backends_add(
    name: str = typer.Option(..., "--name", "-n", help="Backend name"),
    command: str = typer.Option(..., "--command", "-c", help="Command to execute the backend"),
):
    """Add a custom agent backend."""
    try:
        result = client.post("/api/computer-use/backends", json={"name": name, "command": command})
        console.print(f"[green]Added backend: {name}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@models_app.command("compare")
def models_compare(
    prompt: str = typer.Option(..., "--prompt", "-p", help="Prompt to compare"),
    models_str: str = typer.Option(..., "--models", "-m", help="Comma-separated model names"),
):
    """Compare responses across multiple models."""
    model_list = [m.strip() for m in models_str.split(",")]
    try:
        result = client.post("/api/compare", json={"prompt": prompt, "models": model_list})
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    results = result.get("results", [])
    for r in results:
        console.print(f"\n[bold]{r['model']}[/bold] ({r.get('provider', '?')})")
        console.print(f"  Tokens: {r.get('input_tokens', 0)} in / {r.get('output_tokens', 0)} out")
        console.print(f"  Latency: {r.get('latency_ms', 0)}ms | Cost: ${r.get('cost', 0):.4f}")
        if r.get("error"):
            console.print(f"  [red]Error: {r['error']}[/red]")
        else:
            console.print(Panel(r.get("content", "")[:500], border_style="dim"))


# --- Workspace commands ---

workspace_app = typer.Typer(help="Manage workspaces")
app.add_typer(workspace_app, name="workspace")


def _resolve_workspace(name: str) -> dict:
    """Look up a workspace by name. Returns the workspace dict or exits."""
    try:
        workspaces = client.get("/api/workspaces")
    except Exception as e:
        console.print(f"[red]Error fetching workspaces: {e}[/red]")
        raise typer.Exit(1)

    for ws in workspaces:
        if ws.get("name") == name:
            return ws

    console.print(f"[red]Workspace '{name}' not found.[/red]")
    names = [ws.get("name", "?") for ws in workspaces]
    if names:
        console.print(f"[dim]Available: {', '.join(names)}[/dim]")
    raise typer.Exit(1)


@workspace_app.command("create")
def workspace_create(
    name: str = typer.Argument(..., help="Workspace name"),
):
    """Create a new workspace."""
    try:
        result = client.post("/api/workspaces", json={"name": name})
        console.print(f"[green]Created workspace '{name}'[/green]")
        if result.get("id"):
            console.print(f"  ID: {result['id']}")
        if result.get("path"):
            console.print(f"  Path: {result['path']}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@workspace_app.command("list")
def workspace_list():
    """List all workspaces."""
    try:
        workspaces = client.get("/api/workspaces")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not workspaces:
        console.print("[dim]No workspaces found.[/dim]")
        return

    table = Table(title="Workspaces")
    table.add_column("Name", style="bold")
    table.add_column("Path", style="dim")
    table.add_column("Status")
    table.add_column("Created")

    for ws in workspaces:
        status = ws.get("status", "unknown")
        status_color = {"active": "green", "archived": "yellow", "error": "red"}.get(status, "white")
        table.add_row(
            ws.get("name", "?"),
            ws.get("path", "?"),
            f"[{status_color}]{status}[/{status_color}]",
            ws.get("created", "?"),
        )

    console.print(table)


@workspace_app.command("delete")
def workspace_delete(
    name: str = typer.Argument(..., help="Workspace name to delete"),
):
    """Delete a workspace by name."""
    ws = _resolve_workspace(name)
    typer.confirm(f"Delete workspace '{name}'?", abort=True)
    try:
        client.delete(f"/api/workspaces/{ws['id']}")
        console.print(f"[green]Deleted workspace '{name}'[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


def _build_file_tree(files: list, tree: Tree, prefix: str = ""):
    """Recursively build a Rich Tree from a flat list of file paths."""
    # Group files by top-level directory component
    dirs: dict[str, list] = {}
    plain_files: list[str] = []

    for f in files:
        path = f.get("path", f) if isinstance(f, dict) else f
        # Strip leading prefix
        rel = path[len(prefix):].lstrip("/") if prefix and path.startswith(prefix) else path
        if "/" in rel:
            top, rest = rel.split("/", 1)
            dirs.setdefault(top, []).append(rest)
        else:
            plain_files.append(rel)

    for d in sorted(dirs.keys()):
        branch = tree.add(f"[bold blue]{d}/[/bold blue]")
        # Rebuild as simple path strings for recursion
        child_files = [{"path": p} for p in dirs[d]]
        _build_file_tree(child_files, branch)

    for f in sorted(plain_files):
        tree.add(f"[green]{f}[/green]")


@workspace_app.command("files")
def workspace_files(
    name: str = typer.Argument(..., help="Workspace name"),
    tree: bool = typer.Option(False, "--tree", "-t", help="Show as tree instead of flat list"),
):
    """List files in a workspace."""
    ws = _resolve_workspace(name)
    try:
        files = client.get(f"/api/workspaces/{ws['id']}/files")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not files:
        console.print("[dim]No files in workspace.[/dim]")
        return

    if tree:
        rtree = Tree(f"[bold]{name}[/bold]")
        _build_file_tree(files, rtree)
        console.print(rtree)
    else:
        for f in files:
            path = f.get("path", f) if isinstance(f, dict) else f
            console.print(path)


@workspace_app.command("read")
def workspace_read(
    name: str = typer.Argument(..., help="Workspace name"),
    path: str = typer.Argument(..., help="File path within the workspace"),
):
    """Read a file from a workspace with syntax highlighting."""
    ws = _resolve_workspace(name)
    try:
        result = client.get(f"/api/workspaces/{ws['id']}/files/{path}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    content = result.get("content", result) if isinstance(result, dict) else str(result)

    # Detect language from file extension for syntax highlighting
    ext = path.rsplit(".", 1)[-1] if "." in path else ""
    lang_map = {
        "py": "python", "js": "javascript", "ts": "typescript", "tsx": "tsx",
        "jsx": "jsx", "json": "json", "yaml": "yaml", "yml": "yaml",
        "toml": "toml", "md": "markdown", "sh": "bash", "bash": "bash",
        "rs": "rust", "go": "go", "rb": "ruby", "sql": "sql",
        "html": "html", "css": "css", "xml": "xml", "dockerfile": "dockerfile",
    }
    lang = lang_map.get(ext.lower(), "text")

    syntax = Syntax(str(content), lang, theme="monokai", line_numbers=True)
    console.print(syntax)


@workspace_app.command("write")
def workspace_write(
    name: str = typer.Argument(..., help="Workspace name"),
    path: str = typer.Argument(..., help="File path within the workspace"),
    content: str = typer.Option("", "--content", "-c", help="Content to write (inline)"),
    file: str = typer.Option("", "--file", "-f", help="Read content from a local file"),
):
    """Write a file to a workspace."""
    if not content and not file:
        console.print("[red]Provide --content or --file.[/red]")
        raise typer.Exit(1)

    if file:
        source = Path(file)
        if not source.exists():
            console.print(f"[red]File not found: {file}[/red]")
            raise typer.Exit(1)
        content = source.read_text()

    ws = _resolve_workspace(name)
    try:
        client.put(f"/api/workspaces/{ws['id']}/files/{path}", json={"content": content})
        console.print(f"[green]Wrote {path} to workspace '{name}'[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@workspace_app.command("search")
def workspace_search(
    name: str = typer.Argument(..., help="Workspace name"),
    query: str = typer.Argument(..., help="Search query"),
):
    """Search files in a workspace."""
    ws = _resolve_workspace(name)
    try:
        results = client.post(f"/api/workspaces/{ws['id']}/files/search", json={"query": query})
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    matches = results if isinstance(results, list) else results.get("matches", results.get("results", []))
    if not matches:
        console.print("[dim]No matches found.[/dim]")
        return

    for match in matches:
        if isinstance(match, dict):
            filepath = match.get("path", match.get("file", "?"))
            line = match.get("line", "")
            snippet = match.get("snippet", match.get("content", ""))
            loc = f"{filepath}:{line}" if line else filepath
            console.print(f"[bold cyan]{loc}[/bold cyan]")
            if snippet:
                console.print(f"  {snippet.strip()}")
        else:
            console.print(str(match))


@workspace_app.command("open")
def workspace_open(
    name: str = typer.Argument(..., help="Workspace name"),
    tmux: bool = typer.Option(False, "--tmux", help="Open in a tmux session with 3 panes"),
):
    """Print workspace path or open in tmux session.

    Usage:
        cd $(forge workspace open myproject)
        forge workspace open myproject --tmux
    """
    ws = _resolve_workspace(name)
    ws_path = ws.get("path", "")

    if not ws_path:
        console.print("[red]Workspace has no path set.[/red]")
        raise typer.Exit(1)

    if tmux:
        session_name = f"af-{name}"
        # Create tmux session with 3 panes: editor + dashboard + shell
        try:
            # Create session with first pane (editor placeholder)
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", session_name, "-c", ws_path],
                check=True,
            )
            # Split horizontally for dashboard pane
            subprocess.run(
                ["tmux", "split-window", "-h", "-t", session_name, "-c", ws_path],
                check=True,
            )
            # Split the right pane vertically for shell
            subprocess.run(
                ["tmux", "split-window", "-v", "-t", session_name, "-c", ws_path],
                check=True,
            )
            # Select the first pane
            subprocess.run(
                ["tmux", "select-pane", "-t", f"{session_name}:0.0"],
                check=True,
            )
            console.print(f"[green]tmux session '{session_name}' created with 3 panes.[/green]")
            console.print(f"  Attach with: [bold]tmux attach -t {session_name}[/bold]")
        except FileNotFoundError:
            console.print("[red]tmux is not installed.[/red]")
            raise typer.Exit(1)
        except subprocess.CalledProcessError as e:
            console.print(f"[red]tmux error: {e}[/red]")
            raise typer.Exit(1)
    else:
        # Print path only (no Rich markup) so it works with cd $()
        print(ws_path)


@workspace_app.command("history")
def workspace_history(
    name: str = typer.Argument(..., help="Workspace name"),
    path: str = typer.Option("", "--path", "-p", help="Filter history to a specific file"),
):
    """Show workspace history, optionally filtered by file path."""
    ws = _resolve_workspace(name)
    try:
        params = {}
        if path:
            params["path"] = path
        history = client.get(f"/api/workspaces/{ws['id']}/history", params=params)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    entries = history if isinstance(history, list) else history.get("entries", history.get("history", []))
    if not entries:
        console.print("[dim]No history found.[/dim]")
        return

    table = Table(title=f"History — {name}" + (f" ({path})" if path else ""))
    table.add_column("Timestamp", style="dim")
    table.add_column("Action", style="bold")
    table.add_column("Path")
    table.add_column("Details")

    for entry in entries:
        if isinstance(entry, dict):
            table.add_row(
                entry.get("timestamp", entry.get("created", "?")),
                entry.get("action", entry.get("type", "?")),
                entry.get("path", ""),
                entry.get("details", entry.get("message", "")),
            )
        else:
            table.add_row(str(entry), "", "", "")

    console.print(table)


if __name__ == "__main__":
    app()

