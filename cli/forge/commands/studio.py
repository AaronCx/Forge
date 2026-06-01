"""Forge CLI — studio commands (split from main.py in PR-1).

PR-1 is a mechanical refactor — zero behavior change. Each module owns a private
_app typer that captures the flat root-level commands; register(parent) forwards
them and attaches any sub-apps in this module.
"""

import json
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree

from forge import client
from forge.config import (
    get_api_key,
)

PIDS_FILE = Path.home() / ".forge" / "pids.json"

console = Console()


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


def _build_file_tree(files: list, tree: Tree, prefix: str = ""):
    """Recursively build a Rich Tree from a flat list of file paths."""
    dirs: dict[str, list] = {}
    plain_files: list[str] = []

    for f in files:
        path = f.get("path", f) if isinstance(f, dict) else f
        rel = path[len(prefix):].lstrip("/") if prefix and path.startswith(prefix) else path
        if "/" in rel:
            top, rest = rel.split("/", 1)
            dirs.setdefault(top, []).append(rest)
        else:
            plain_files.append(rel)

    for d in sorted(dirs.keys()):
        branch = tree.add(f"[bold blue]{d}/[/bold blue]")
        child_files = [{"path": p} for p in dirs[d]]
        _build_file_tree(child_files, branch)

    for f in sorted(plain_files):
        tree.add(f"[green]{f}[/green]")


_app = typer.Typer()

agents_app = typer.Typer(help="Manage agents")



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
        # The /api/agents/<id>/run endpoint is a POST that takes the token
        # and input_text as query parameters. Using stream_sse (GET) returned
        # 405 Method Not Allowed, so the CLI run flow never produced any
        # output. Build the query string and use stream_sse_post.
        from urllib.parse import urlencode
        qs = urlencode({"token": get_api_key(), "input_text": input_text})
        for data_str in client.stream_sse_post(f"/api/agents/{agent_id}/run?{qs}"):
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


blueprints_app = typer.Typer(help="Manage blueprints")



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


prompts_app = typer.Typer(help="Manage prompt versions")



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


@agents_app.command("history")
def agents_history(
    agent_id: str = typer.Argument(..., help="Agent ID"),
):
    """Show run history for an agent."""
    try:
        runs = client.get("/api/runs", params={"agent_id": agent_id, "limit": "20"})
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


workspace_app = typer.Typer(help="Manage workspaces")



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


def register(parent: typer.Typer) -> None:
    """Forward this module's flat commands and sub-apps onto the root app."""
    for cmd_info in _app.registered_commands:
        parent.registered_commands.append(cmd_info)
    parent.add_typer(agents_app, name="agents")


    parent.add_typer(blueprints_app, name="blueprints")


    parent.add_typer(prompts_app, name="prompts")


    parent.add_typer(knowledge_app, name="knowledge")


    parent.add_typer(workspace_app, name="workspace")


