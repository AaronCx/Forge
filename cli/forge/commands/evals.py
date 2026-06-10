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

optimize_app = typer.Typer(help="Eval-driven self-optimization of agent prompts")



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


@optimize_app.command("run")
def optimize_run(
    agent_id: str = typer.Argument(..., help="Agent ID to optimize"),
    suite_id: str = typer.Option(..., "--suite", "-s", help="Eval suite ID (must target the agent)"),
    n_variants: int = typer.Option(3, "--variants", "-n", help="Number of prompt variants to try"),
    model: str = typer.Option("", "--model", "-m", help="Override model for evals/generation"),
):
    """Run a self-optimization attempt: baseline eval, generate + score variants, gate the winner."""
    console.print(f"[bold]Optimizing agent {agent_id[:8]} against suite {suite_id[:8]}...[/bold]")
    try:
        body: dict = {"agent_id": agent_id, "suite_id": suite_id, "n_variants": n_variants}
        if model:
            body["model"] = model
        result = client.post("/api/optimizer/runs", json=body)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    status = result.get("status", "?")
    console.print(f"  Status: [bold]{status}[/bold]")
    console.print(f"  Baseline score: {result.get('baseline_score') or 0:.3f}")
    if result.get("winner_score") is not None:
        console.print(f"  Winner score: {result.get('winner_score') or 0:.3f}")
        console.print(f"  Delta: [green]{result.get('score_delta') or 0:+.3f}[/green]")
    if result.get("summary"):
        console.print(f"  {result['summary']}")
    if status == "awaiting_approval":
        console.print(
            f"\n[yellow]Winner is gated behind approval {str(result.get('approval_id', ''))[:8]}.[/yellow]"
        )
        console.print("  Approve it (forge ops approvals) then: "
                      f"forge evals optimize apply {result.get('approval_id', '')[:8]}...")
    console.print(f"  Run ID: {result.get('id', '')[:8]}")


@optimize_app.command("list")
def optimize_list(
    agent_id: str = typer.Option("", "--agent", "-a", help="Filter by agent ID"),
):
    """List optimization runs (lineage)."""
    try:
        params = {"agent_id": agent_id} if agent_id else None
        runs = client.get("/api/optimizer/runs", params=params)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not runs:
        console.print("[dim]No optimization runs.[/dim]")
        return

    table = Table(title="Optimization Runs")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Agent", style="dim", max_width=8)
    table.add_column("Status")
    table.add_column("Baseline", justify="right")
    table.add_column("Winner", justify="right")
    table.add_column("Delta", justify="right")
    for r in runs:
        base = f"{r['baseline_score']:.3f}" if r.get("baseline_score") is not None else "—"
        win = f"{r['winner_score']:.3f}" if r.get("winner_score") is not None else "—"
        delta = f"{r['score_delta']:+.3f}" if r.get("score_delta") is not None else "—"
        table.add_row(r["id"][:8], (r.get("agent_id") or "")[:8], r.get("status", "?"), base, win, delta)
    console.print(table)


@optimize_app.command("show")
def optimize_show(
    run_id: str = typer.Argument(..., help="Optimization run ID"),
):
    """Show an optimization run with its variant lineage."""
    try:
        run = client.get(f"/api/optimizer/runs/{run_id}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]Optimization Run {run['id'][:8]}[/bold]")
    console.print(f"  Status: {run.get('status', '?')}")
    console.print(f"  Baseline score: {run.get('baseline_score') or 0:.3f}")
    if run.get("summary"):
        console.print(f"  {run['summary']}")

    variants = run.get("variants", [])
    if variants:
        table = Table(title="Variants")
        table.add_column("Idx", justify="right")
        table.add_column("Score", justify="right")
        table.add_column("Pass rate", justify="right")
        table.add_column("Winner")
        for v in variants:
            table.add_row(
                str(v.get("variant_index", "?")),
                f"{v.get('score') or 0:.3f}",
                f"{(v.get('pass_rate') or 0) * 100:.0f}%",
                "[green]★[/green]" if v.get("is_winner") else "",
            )
        console.print(table)
    console.print()


@optimize_app.command("apply")
def optimize_apply(
    approval_id: str = typer.Argument(..., help="Approved optimization approval ID"),
):
    """Promote an approved optimization winner to the agent's active prompt."""
    try:
        result = client.post(f"/api/optimizer/approvals/{approval_id}/apply")
        console.print(f"[green]Promoted to prompt version {result.get('version_number', '?')}.[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# Attach the optimize sub-app at module import — main.py mounts evals_app directly
# (it does not call register()), so sub-apps must be wired here.
evals_app.add_typer(optimize_app, name="optimize")


def register(parent: typer.Typer) -> None:
    """Forward this module's flat commands and sub-apps onto the root app."""
    for cmd_info in _app.registered_commands:
        parent.registered_commands.append(cmd_info)
    parent.add_typer(evals_app, name="evals")


