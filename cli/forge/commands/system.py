"""Forge CLI — system commands (split from main.py in PR-1).

PR-1 is a mechanical refactor — zero behavior change. Each module owns a private
_app typer that captures the flat root-level commands; register(parent) forwards
them and attaches any sub-apps in this module.
"""

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from forge import __version__, client
from forge.config import (
    get_api_url,
)

PIDS_FILE = Path.home() / ".forge" / "pids.json"

console = Console()

_app = typer.Typer()

@_app.command()
def version():
    """Show CLI version."""
    console.print(f"forge-cli v{__version__}")


@_app.command()
def init():
    """Initialize CLI configuration."""
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


@_app.command()
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


@_app.command()
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


@_app.command()
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


@_app.command()
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


@_app.command()
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


@_app.command()
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


@_app.command()
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


def register(parent: typer.Typer) -> None:
    """Forward this module's flat commands and sub-apps onto the root app."""
    for cmd_info in _app.registered_commands:
        parent.registered_commands.append(cmd_info)
