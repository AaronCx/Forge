"""Forge CLI — saved dynamic workflows (Phase 9.6).

`forge workflows list` shows workflows saved from plan cards; `run` re-executes
one (identical structure, fresh sub-agents); `save` persists a proposed plan
from a session's log.
"""

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from forge import client

console = Console()

workflows_app = typer.Typer(help="List, run, and save dynamic workflows")


@workflows_app.command("list")
def list_workflows() -> None:
    """List workflows saved to the blueprint library."""
    rows = client.get("/api/workflows")
    if not rows:
        console.print("[dim]No saved workflows. Save one from a plan card or "
                      "`forge workflows save`.[/dim]")
        return
    table = Table(title="Saved workflows")
    table.add_column("id", style="dim")
    table.add_column("name")
    table.add_column("agents", justify="right")
    table.add_column("stages", justify="right")
    for row in rows:
        spec = row.get("workflow_spec") or {}
        stages = spec.get("stages", [])
        agents = sum(len(s.get("agents", [])) for s in stages)
        table.add_row(row.get("id", "")[:8], row.get("name", ""),
                      str(agents), str(len(stages)))
    console.print(table)


@workflows_app.command("run")
def run_workflow(
    workflow_id: str = typer.Argument(..., help="Saved workflow (blueprint) id"),
    session: str = typer.Option("", "--session", "-s",
                                help="Attach to an existing session id"),
    goal: str = typer.Option("", "--goal", "-g", help="Optional goal/input text"),
) -> None:
    """Re-run a saved workflow, streaming its progress."""
    from forge.commands.chat import _stream_workflow_run

    body: dict = {"goal": goal}
    if session:
        body["session_id"] = session
    for data in client.stream_sse_post(f"/api/workflows/{workflow_id}/run", json=body):
        if data == "[DONE]":
            break
        try:
            event = _json.loads(data)
        except _json.JSONDecodeError:
            continue
        _print_run_event(event)


def _print_run_event(event: dict) -> None:
    etype = event.get("type")
    d = event.get("data") or {}
    if etype == "workflow_started":
        console.print(f"[green]▶ running[/green] {d.get('title', '')}")
    elif etype == "workflow_progress":
        console.print(
            f"[dim]  {d.get('stage_id')}: {d.get('agents_done')}/"
            f"{d.get('agents_total')} done · {d.get('tokens_spent', 0):,} tok · "
            f"{d.get('elapsed_seconds')}s[/dim]"
        )
    elif etype == "workflow_error":
        console.print(f"[red]✗ {d.get('error')}[/red]")
    elif etype == "workflow_done":
        colour = "green" if d.get("status") == "completed" else "red"
        console.print(f"[{colour}]■ {d.get('status')}[/{colour}]")
        if d.get("output"):
            console.print(str(d["output"]))
    elif etype == "error":
        console.print(f"[red]{event.get('data')}[/red]")


@workflows_app.command("save")
def save_workflow(
    session: str = typer.Option(..., "--session", "-s", help="Session id"),
    plan_seq: int = typer.Option(..., "--plan", "-p", help="Plan event seq"),
    name: str = typer.Option("", "--name", "-n", help="Library name"),
) -> None:
    """Save a proposed plan from a session's log to the library."""
    saved = client.post(f"/api/sessions/{session}/workflow/save",
                        json={"plan_seq": plan_seq, "name": name})
    console.print(f"[green]Saved:[/green] {saved.get('name')} ({saved.get('id', '')[:8]})")


def register(parent: typer.Typer) -> None:
    parent.add_typer(workflows_app, name="workflows")
