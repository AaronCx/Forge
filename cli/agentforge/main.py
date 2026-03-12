"""AgentForge CLI — main entry point."""

import json
import time
import typer
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text

from agentforge import __version__
from agentforge import client
from agentforge.config import ensure_config, get_api_url

app = typer.Typer(
    name="agentforge",
    help="AgentForge CLI — manage and monitor AI agents from the terminal.",
    no_args_is_help=True,
)
console = Console()

agents_app = typer.Typer(help="Manage agents")
app.add_typer(agents_app, name="agents")


@app.command()
def version():
    """Show CLI version."""
    console.print(f"agentforge-cli v{__version__}")


@app.command()
def init():
    """Initialize CLI configuration."""
    ensure_config()
    console.print(f"[green]Config created at ~/.agentforge/config.toml[/green]")
    console.print(f"Set your api_url and api_key in the config file.")


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
            return Panel(f"[red]Error: {e}[/red]", title="AgentForge Dashboard")

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

        return Panel(layout, title="AgentForge Dashboard", subtitle="Ctrl+C to quit")

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
    from agentforge.config import get_api_key

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
                    console.print(f"\n[bold green]Result[/bold green]")
                    console.print(Panel(event["data"], border_style="green"))
                    group_id = event.get("group_id", "")
                    if group_id:
                        console.print(f"[dim]Group ID: {group_id}[/dim]")

            except json.JSONDecodeError:
                pass
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


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
    console.print(f"[bold]Monthly Projection[/bold]")
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


if __name__ == "__main__":
    app()
