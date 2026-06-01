"""Forge CLI — evals commands (split from main.py in PR-1).

PR-1 is a mechanical refactor — zero behavior change. Each module owns a private
_app typer that captures the flat root-level commands; register(parent) forwards
them and attaches any sub-apps in this module.
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from forge import client

PIDS_FILE = Path.home() / ".forge" / "pids.json"

console = Console()

_app = typer.Typer()

evals_app = typer.Typer(help="Manage eval suites and runs")



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


@_app.command()
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


def register(parent: typer.Typer) -> None:
    """Forward this module's flat commands and sub-apps onto the root app."""
    for cmd_info in _app.registered_commands:
        parent.registered_commands.append(cmd_info)
    parent.add_typer(evals_app, name="evals")


