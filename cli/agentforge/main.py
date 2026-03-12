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
                    console.print(f"\n[bold green]Blueprint complete[/bold green]")
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


messages_app = typer.Typer(help="View inter-agent messages")
app.add_typer(messages_app, name="messages")


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
            from agentforge.config import get_api_url
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
        console.print(f"[green]Eval complete![/green]")
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
        console.print(f"\n[bold]By type:[/bold]")
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
        console.print(f"\n[bold]Input:[/bold]")
        console.print(Panel(tree["input_preview"][:500], border_style="dim"))

    if tree.get("output_preview"):
        console.print(f"\n[bold]Output:[/bold]")
        console.print(Panel(tree["output_preview"][:500], border_style="green"))

    if tree.get("error_message"):
        console.print(f"\n[bold red]Error:[/bold red]")
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
    console.print(f"[dim]Searching...[/dim]")
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


if __name__ == "__main__":
    app()

