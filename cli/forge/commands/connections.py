"""Forge CLI — connections commands (split from main.py in PR-1).

PR-1 is a mechanical refactor — zero behavior change. Each module owns a private
_app typer that captures the flat root-level commands; register(parent) forwards
them and attaches any sub-apps in this module.
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forge import client

PIDS_FILE = Path.home() / ".forge" / "pids.json"

console = Console()


def _steer(*args: str) -> dict:
    """Invoke the local steer binary and return its parsed JSON output.

    The CU CLI commands historically posted to /api/blueprints/node-exec, an
    endpoint that does not exist in any router (QA Finding #30). Steer is a
    local binary installed by `scripts/bootstrap-macos.sh`; calling it
    directly is the documented architecture and avoids the round-trip
    entirely.
    """
    import json
    import shutil
    import subprocess

    binary = shutil.which("steer") or str(Path.home() / "bin" / "steer")
    if not Path(binary).exists():
        raise RuntimeError(
            "steer binary not found — run scripts/bootstrap-macos.sh first"
        )
    try:
        result = subprocess.run(
            [binary, *args], capture_output=True, text=True, check=True, timeout=30
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"steer {' '.join(args)} failed: {exc.stderr.strip() or exc.stdout.strip()}"
        ) from exc
    output = (result.stdout or "").strip()
    if not output:
        return {"success": True}
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"success": True, "raw": output}


_app = typer.Typer()

models_app = typer.Typer(help="Manage models and providers")



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


@models_app.command("cards")
def models_cards():
    """Show model cards (data-driven capabilities) merged with your overrides."""
    try:
        cards = client.get("/api/providers/model-cards")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not cards:
        console.print("[dim]No model cards available.[/dim]")
        return

    table = Table(title="Model Cards")
    table.add_column("Model ID", style="bold")
    table.add_column("Provider")
    table.add_column("Context", justify="right")
    table.add_column("Vision")
    table.add_column("Tools")
    table.add_column("Thinking")
    for c in cards:
        table.add_row(
            c["id"],
            c["provider"],
            f"{c['context_window']:,}",
            "Yes" if c.get("vision") else "No",
            "Yes" if c.get("tools") else "No",
            "Yes" if c.get("thinking") else "No",
        )
    console.print(table)


@models_app.command("refresh")
def models_refresh():
    """Pull each configured provider's live model list into your model cards."""
    try:
        cards = client.post("/api/providers/models/refresh")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Refreshed model cards.[/green] {len(cards)} models known.")


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


@mcp_app.command("add")
def mcp_add(
    name: str = typer.Option(..., "--name", "-n", help="Connection name"),
    transport: str = typer.Option("stdio", "--transport", "-t", help="stdio or http"),
    command: str = typer.Option("", "--command", "-c", help="stdio: command to run"),
    args: list[str] = typer.Option([], "--arg", "-a", help="stdio: command arg (repeatable)"),
    url: str = typer.Option("", "--url", "-u", help="http: server URL"),
    token: str = typer.Option("", "--token", help="http: OAuth bearer token"),
):
    """Add a real MCP server (JSON-RPC 2.0) over stdio or Streamable HTTP."""
    body: dict = {"name": name, "transport": transport, "command": command,
                  "args": list(args), "url": url}
    if token:
        body["oauth"] = {"access_token": token}
    try:
        result = client.post("/api/mcp/connect-v2", json=body)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    tools = result.get("tools_discovered", [])
    console.print(f"[green]Connected to {result['name']} ({transport})[/green]")
    console.print(f"  Tools discovered: {len(tools)}")
    for t in tools[:10]:
        console.print(f"    - {t['name']}: {t.get('description', '')[:60]}")


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


cu_app = typer.Typer(help="Computer use — GUI and terminal automation")




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
        args = ["see"]
        if app_name and app_name != "screen":
            args += ["--app", app_name]
        result = _steer(*args)
        path = result.get("path") or result.get("screenshot_path") or ""
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
        args = ["ocr"]
        if app_name and app_name != "screen":
            args += ["--app", app_name]
        result = _steer(*args)
        # steer ocr emits a JSON array of regions; older paths returned a dict
        # with `text`/`element_count`. Handle both.
        if isinstance(result, list):
            elements = result
            text = "\n".join(e.get("text", "") for e in elements if isinstance(e, dict))
        elif isinstance(result, dict):
            elements = result.get("elements") or []
            text = result.get("text", "")
        else:
            elements, text = [], ""
        console.print(f"[dim]({len(elements)} elements detected)[/dim]")
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
        _steer("click", str(x), str(y))
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
        _steer("type", text)
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
        _steer("hotkey", keys)
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


tools_app = typer.Typer(help="List available tools (built-in and MCP)")



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


def register(parent: typer.Typer) -> None:
    """Forward this module's flat commands and sub-apps onto the root app."""
    for cmd_info in _app.registered_commands:
        parent.registered_commands.append(cmd_info)
    parent.add_typer(models_app, name="models")


    parent.add_typer(mcp_app, name="mcp")


    parent.add_typer(cu_app, name="computer-use")
    parent.add_typer(cu_app, name="cu")


    parent.add_typer(targets_app, name="targets")


    parent.add_typer(tools_app, name="tools")


