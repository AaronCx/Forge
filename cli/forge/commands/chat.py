"""Forge CLI — chat sessions (harness-plan.md Phase 6).

`forge chat` is an interactive REPL over a durable session; `forge agent run`
is a headless one-shot that emits one JSON StreamEvent per line for CI use.
Requires FORGE_SESSIONS enabled on the server.
"""

import json as _json
import sys

import typer
from rich.console import Console

from forge import client

console = Console()

chat_app = typer.Typer(help="Chat with any model over durable sessions")


def _print_plan_card(data: dict) -> None:
    """Render a proposed workflow plan (the CLI's plan card)."""
    spec = data.get("spec") or {}
    console.print(f"\n[bold magenta]Workflow plan:[/bold magenta] {spec.get('title', '')}")
    if spec.get("rationale"):
        console.print(f"[dim]{spec['rationale']}[/dim]")
    for stage in spec.get("stages", []):
        agents = stage.get("agents", [])
        deps = f" ← {', '.join(stage.get('depends_on', []))}" if stage.get("depends_on") else ""
        console.print(
            f"  [cyan]{stage.get('id')}[/cyan] ({stage.get('kind', 'single')}, "
            f"{len(agents)} agent{'s' if len(agents) != 1 else ''}){deps}"
        )
        for agent in agents:
            console.print(f"    · {agent.get('role', 'worker')}: "
                          f"[dim]{str(agent.get('prompt', ''))[:80]}[/dim]")
    console.print(
        f"[dim]worker model: {spec.get('worker_model') or 'session default'} · "
        f"~{data.get('estimated_tokens', 0):,} tokens estimated[/dim]"
    )


def _stream_workflow_run(session_id: str, body: dict, agent_count: int) -> None:
    """Run a consented plan and print the live progress strip."""
    for data in client.stream_sse_post(
        f"/api/sessions/{session_id}/workflow/run", json={**body, "confirm": True}
    ):
        if data == "[DONE]":
            break
        try:
            event = _json.loads(data)
        except _json.JSONDecodeError:
            continue
        etype = event.get("type")
        d = event.get("data") or {}
        if etype == "workflow_started":
            console.print(f"[green]▶ running[/green] {d.get('title', '')} "
                          f"({agent_count} agents)")
        elif etype == "workflow_progress":
            console.print(
                f"[dim]  {d.get('stage_id')}: {d.get('agents_done')}/"
                f"{d.get('agents_total')} done, {d.get('agents_running')} running · "
                f"{d.get('tokens_spent', 0):,} tok · {d.get('elapsed_seconds')}s[/dim]"
            )
        elif etype == "workflow_error":
            console.print(f"[red]✗ {d.get('node_id', '')}: {d.get('error')}[/red]")
        elif etype == "workflow_done":
            colour = "green" if d.get("status") == "completed" else "red"
            console.print(f"[{colour}]■ {d.get('status')}[/{colour}] "
                          f"({d.get('tokens_spent', 0):,} tokens, "
                          f"{d.get('elapsed_seconds')}s)")
            if d.get("output"):
                console.print(str(d["output"]))
        elif etype == "error":
            console.print(f"[red]{event.get('data')}[/red]")


def _handle_plan(session_id: str, data: dict) -> None:
    """The consent prompt for a proposed plan: y (run) / e (edit) / s (save) / n."""
    _print_plan_card(data)
    spec = data.get("spec") or {}
    plan_seq = data.get("seq")
    agent_count = sum(len(s.get("agents", [])) for s in spec.get("stages", []))
    while True:
        try:
            choice = console.input(
                "[bold]Run this workflow?[/bold] [y]es / [e]dit / [s]ave / [n]o › "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = "n"
        if choice in ("y", "yes"):
            _stream_workflow_run(session_id, {"plan_seq": plan_seq}, agent_count)
            return
        if choice in ("s", "save"):
            saved = client.post(f"/api/sessions/{session_id}/workflow/save",
                                json={"plan_seq": plan_seq})
            console.print(f"[green]Saved to library:[/green] {saved.get('name')} "
                          f"({saved.get('id', '')[:8]})")
            return
        if choice in ("e", "edit"):
            import os
            import subprocess
            import tempfile

            with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False
            ) as f:
                _json.dump(spec, f, indent=2)
                path = f.name
            subprocess.call([os.environ.get("EDITOR", "vi"), path])
            with open(path) as f:
                try:
                    edited = _json.load(f)
                except _json.JSONDecodeError as exc:
                    console.print(f"[red]Invalid JSON: {exc} — plan unchanged[/red]")
                    continue
            os.unlink(path)
            agent_count = sum(len(s.get("agents", [])) for s in edited.get("stages", []))
            _stream_workflow_run(session_id, {"spec": edited}, agent_count)
            return
        if choice in ("n", "no", ""):
            console.print("[dim]Plan dismissed.[/dim]")
            return


def _stream_turn(session_id: str, text: str, model: str = "") -> None:
    """Stream one turn and print assistant tokens to stdout."""
    body: dict = {"text": text}
    if model:
        body["model"] = model
    plan: dict | None = None
    for data in client.stream_sse_post(f"/api/sessions/{session_id}/messages", json=body):
        if data == "[DONE]":
            break
        try:
            event = _json.loads(data)
        except _json.JSONDecodeError:
            continue
        etype = event.get("type")
        if etype == "token":
            console.print(event.get("data", ""), end="")
        elif etype == "tool_use":
            console.print(f"\n[dim]→ {event['data'].get('name')}[/dim]")
        elif etype == "tool_result":
            mark = "✗" if event["data"].get("is_error") else "✓"
            console.print(f"[dim]{mark} {event['data'].get('tool')}[/dim]")
        elif etype == "workflow_plan":
            plan = event.get("data") or {}
        elif etype == "error":
            console.print(f"\n[red]{event.get('data')}[/red]")
    console.print()
    if plan is not None:
        _handle_plan(session_id, plan)


@chat_app.callback(invoke_without_command=True)
def chat(
    ctx: typer.Context,
    model: str = typer.Option("", "--model", "-m", help="Model for the session"),
    resume: str = typer.Option("", "--resume", "-r", help="Resume an existing session id"),
    workspace: str = typer.Option("", "--workspace", "-w", help="Workspace root"),
    effort: str = typer.Option(
        "standard", "--effort", "-e",
        help="Planner effort: standard | high | ultra (ultra auto-plans workflows)",
    ),
):
    """Start (or resume) an interactive chat session."""
    if ctx.invoked_subcommand is not None:
        return
    if effort not in ("standard", "high", "ultra"):
        console.print("[red]--effort must be standard, high, or ultra[/red]")
        raise typer.Exit(1)
    try:
        if resume:
            session_id = resume
        else:
            session = client.post("/api/sessions", json={
                "model": model, "workspace_root": workspace, "title": "CLI chat",
                "effort": effort})
            session_id = session["id"]
            console.print(f"[green]Session {session_id[:8]} started[/green] "
                          f"(model: {model or 'default'}, effort: {effort})")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    console.print("[dim]Type your message. Ctrl-D or 'exit' to quit.[/dim]")
    while True:
        try:
            line = console.input("[bold cyan]you[/bold cyan] › ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            break
        if line.strip().lower() in ("exit", "quit"):
            break
        if not line.strip():
            continue
        console.print("[bold green]forge[/bold green] › ", end="")
        _stream_turn(session_id, line)


agent_app = typer.Typer(help="Run agents")


@agent_app.command("run")
def agent_run(
    prompt: str = typer.Option(..., "--prompt", "-p", help="The prompt"),
    model: str = typer.Option("", "--model", "-m", help="Model to use"),
    json_out: bool = typer.Option(False, "--json", help="Emit one JSON event per line"),
    workspace: str = typer.Option("", "--workspace", "-w", help="Workspace root"),
):
    """Headless one-shot: run a prompt and stream the result."""
    try:
        session = client.post("/api/sessions", json={
            "model": model, "workspace_root": workspace, "title": "headless"})
        session_id = session["id"]
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    body: dict = {"text": prompt}
    if model:
        body["model"] = model
    for data in client.stream_sse_post(f"/api/sessions/{session_id}/messages", json=body):
        if data == "[DONE]":
            break
        if json_out:
            sys.stdout.write(data + "\n")
            sys.stdout.flush()
        else:
            try:
                event = _json.loads(data)
            except _json.JSONDecodeError:
                continue
            if event.get("type") == "token":
                sys.stdout.write(event.get("data", ""))
                sys.stdout.flush()
    if not json_out:
        sys.stdout.write("\n")


def register(parent: typer.Typer) -> None:
    parent.add_typer(chat_app, name="chat")
    parent.add_typer(agent_app, name="agent")
