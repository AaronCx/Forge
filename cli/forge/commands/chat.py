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


def _stream_turn(session_id: str, text: str, model: str = "") -> None:
    """Stream one turn and print assistant tokens to stdout."""
    body: dict = {"text": text}
    if model:
        body["model"] = model
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
        elif etype == "error":
            console.print(f"\n[red]{event.get('data')}[/red]")
    console.print()


@chat_app.callback(invoke_without_command=True)
def chat(
    ctx: typer.Context,
    model: str = typer.Option("", "--model", "-m", help="Model for the session"),
    resume: str = typer.Option("", "--resume", "-r", help="Resume an existing session id"),
    workspace: str = typer.Option("", "--workspace", "-w", help="Workspace root"),
):
    """Start (or resume) an interactive chat session."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        if resume:
            session_id = resume
        else:
            session = client.post("/api/sessions", json={
                "model": model, "workspace_root": workspace, "title": "CLI chat"})
            session_id = session["id"]
            console.print(f"[green]Session {session_id[:8]} started[/green] "
                          f"(model: {model or 'default'})")
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
