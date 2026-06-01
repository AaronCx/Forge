"""Forge CLI — ops commands (split from main.py in PR-1).

PR-1 is a mechanical refactor — zero behavior change. Each module owns a private
_app typer that captures the flat root-level commands; register(parent) forwards
them and attaches any sub-apps in this module.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forge import client

PIDS_FILE = Path.home() / ".forge" / "pids.json"

console = Console()

_app = typer.Typer()

@_app.command()
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



@runs_app.command("list")
def runs_list(
    status: str = typer.Option(
        "",
        "--status",
        "-s",
        help=(
            "Filter to runs in the given lifecycle stage. One of: queued, running, "
            "awaiting-approval, done, failed. Matches the columns on the Operations board."
        ),
    ),
):
    """List agent runs (optionally filtered by lifecycle stage / kanban column)."""
    try:
        runs = client.get("/api/runs")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if status:
        # PR-5: the column → backend status mapping is the inverse of the kanban's
        # mapRunStatus(): queued → pending, running → running, done → completed,
        # failed → failed. "awaiting-approval" is a separate concept driven by the
        # approvals API; for now the CLI returns an empty list (with a hint) since
        # awaiting-approval items aren't carried on the run resource.
        column_map = {
            "queued": "pending",
            "running": "running",
            "done": "completed",
            "failed": "failed",
        }
        if status == "awaiting-approval":
            console.print(
                "[dim]awaiting-approval is sourced from `forge ops approvals list` — "
                "no runs match this status directly.[/dim]"
            )
            return
        target = column_map.get(status)
        if target is None:
            console.print(
                f"[red]Unknown --status: {status}.[/red] "
                f"Pick one of: {', '.join(['queued', 'running', 'awaiting-approval', 'done', 'failed'])}."
            )
            raise typer.Exit(2)
        runs = [r for r in runs if r.get("status") == target]

    if not runs:
        console.print("[dim]No runs found.[/dim]")
        return

    table = Table(title="Agent Runs" + (f" — {status}" if status else ""))
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


messages_app = typer.Typer(help="View inter-agent messages")




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


triggers_app = typer.Typer(help="Manage event triggers")



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


approvals_app = typer.Typer(help="Manage human-in-the-loop approvals")



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


recordings_app = typer.Typer(help="Manage screen recordings of agent sessions")



@recordings_app.command("list")
def recordings_list():
    """List available recordings."""
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


@_app.command()
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


@triggers_app.command("fire")
def triggers_fire(
    trigger_id: str = typer.Argument(..., help="Trigger ID to fire"),
    input_text: str = typer.Option("", "--input", "-i", help="Input text"),
):
    """Manually fire a trigger (for testing)."""
    try:
        result = client.post(f"/api/triggers/{trigger_id}/fire", json={"input": input_text})
        console.print("[green]Trigger fired.[/green]")
        if result.get("run_id"):
            console.print(f"  Run ID: {result['run_id'][:8]}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


def register(parent: typer.Typer) -> None:
    """Forward this module's flat commands and sub-apps onto the root app."""
    for cmd_info in _app.registered_commands:
        parent.registered_commands.append(cmd_info)
    parent.add_typer(orchestrate_app, name="orchestrate-groups")


    parent.add_typer(runs_app, name="runs")


    parent.add_typer(messages_app, name="messages")
    parent.add_typer(messages_app, name="mail")


    parent.add_typer(triggers_app, name="triggers")


    parent.add_typer(approvals_app, name="approvals")


    parent.add_typer(traces_app, name="traces")


    parent.add_typer(recordings_app, name="recordings")


def register_workspace_shortcuts(workspace_app: typer.Typer) -> None:
    """PR-5: add `forge ops approve`/`forge ops reject` convenience shortcuts.

    These wrap the existing approvals_app commands so terminal users can act
    directly from the Operations workspace without typing the extra `approvals`
    segment (the spec wants the kanban's inline Approve/Reject to mirror this).
    """

    @workspace_app.command("approve")
    def ops_approve(
        approval_id: str = typer.Argument(..., help="Approval ID"),
        feedback: str = typer.Option("", "--feedback", "-f", help="Optional feedback"),
    ) -> None:
        """Approve a pending HITL checkpoint (alias for `forge ops approvals approve`)."""
        try:
            client.post(f"/api/approvals/{approval_id}/approve", json={"feedback": feedback})
            console.print(f"[green]Approved {approval_id[:8]}[/green]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)

    @workspace_app.command("reject")
    def ops_reject(
        approval_id: str = typer.Argument(..., help="Approval ID"),
        feedback: str = typer.Option("", "--feedback", "-f", help="Rejection reason"),
    ) -> None:
        """Reject a pending HITL checkpoint (alias for `forge ops approvals reject`)."""
        try:
            client.post(f"/api/approvals/{approval_id}/reject", json={"feedback": feedback})
            console.print(f"[red]Rejected {approval_id[:8]}[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)


