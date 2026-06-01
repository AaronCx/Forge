"""Forge CLI — marketplace commands (split from main.py in PR-1).

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

_app = typer.Typer()

marketplace_app = typer.Typer(help="Browse and publish to the marketplace")



@marketplace_app.command("browse")
def marketplace_browse(
    category: str = typer.Option("", "--category", "-c", help="Filter by category"),
    search_query: str = typer.Option("", "--search", "-s", help="Search by title"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
):
    """Browse marketplace listings."""
    try:
        params: dict = {"limit": str(limit)}
        if category:
            params["category"] = category
        if search_query:
            params["search"] = search_query
        listings = client.get("/api/marketplace/listings", params=params)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not listings:
        console.print("[dim]No listings found.[/dim]")
        return

    table = Table(title="Marketplace")
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Title", style="bold")
    table.add_column("Category")
    table.add_column("Rating", justify="right")
    table.add_column("Forks", justify="right")
    table.add_column("Version", style="dim")

    for li in listings:
        rating = f"{li.get('rating_avg', 0):.1f} ({li.get('rating_count', 0)})"
        table.add_row(
            li["id"][:8],
            li["title"],
            li.get("category", ""),
            rating,
            str(li.get("fork_count", 0)),
            li.get("version", ""),
        )

    console.print(table)


@marketplace_app.command("publish")
def marketplace_publish(
    blueprint_id: str = typer.Option(..., "--blueprint", "-b", help="Blueprint ID to publish"),
    title: str = typer.Option(..., "--title", "-t", help="Listing title"),
    description: str = typer.Option("", "--desc", "-d", help="Description"),
    category: str = typer.Option("general", "--category", "-c", help="Category"),
):
    """Publish a blueprint to the marketplace."""
    try:
        result = client.post("/api/marketplace/listings", json={
            "blueprint_id": blueprint_id,
            "title": title,
            "description": description,
            "category": category,
        })
        console.print(f"[green]Published:[/green] {result['title']} ({result['id'][:8]})")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@marketplace_app.command("rate")
def marketplace_rate(
    listing_id: str = typer.Argument(..., help="Listing ID to rate"),
    rating: int = typer.Option(..., "--rating", "-r", help="Rating 1-5"),
    review: str = typer.Option("", "--review", help="Optional review text"),
):
    """Rate a marketplace listing."""
    if rating < 1 or rating > 5:
        console.print("[red]Rating must be 1-5[/red]")
        raise typer.Exit(1)
    try:
        client.post(f"/api/marketplace/listings/{listing_id}/rate", json={
            "rating": rating,
            "review": review,
        })
        console.print(f"[green]Rated {listing_id[:8]} with {rating}/5[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@marketplace_app.command("fork")
def marketplace_fork(
    listing_id: str = typer.Argument(..., help="Listing ID to fork"),
    blueprint_id: str = typer.Option(..., "--blueprint", "-b", help="New blueprint ID for the fork"),
):
    """Fork a marketplace listing."""
    try:
        result = client.post(f"/api/marketplace/listings/{listing_id}/fork", json={
            "forked_blueprint_id": blueprint_id,
        })
        console.print(f"[green]Forked {listing_id[:8]}[/green] → {result.get('forked_blueprint_id', blueprint_id)[:8]}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@marketplace_app.command("show")
def marketplace_show(
    listing_id: str = typer.Argument(..., help="Listing ID"),
):
    """Show marketplace listing details."""
    try:
        li = client.get(f"/api/marketplace/listings/{listing_id}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    rating = f"{li.get('rating_avg', 0):.1f}/5 ({li.get('rating_count', 0)} ratings)"
    console.print()
    console.print(Panel(
        f"[bold]{li['title']}[/bold]\n"
        f"[dim]ID: {li['id']}[/dim]\n\n"
        f"[bold]Category:[/bold] {li.get('category', '—')}\n"
        f"[bold]Version:[/bold] {li.get('version', '—')}\n"
        f"[bold]Rating:[/bold] {rating}\n"
        f"[bold]Forks:[/bold] {li.get('fork_count', 0)}\n"
        f"[bold]Description:[/bold] {li.get('description', '') or '—'}",
        title="Marketplace Listing",
    ))
    console.print()


@marketplace_app.command("unpublish")
def marketplace_unpublish(
    listing_id: str = typer.Argument(..., help="Listing ID to unpublish"),
):
    """Unpublish a marketplace listing."""
    typer.confirm(f"Unpublish listing {listing_id[:8]}?", abort=True)
    try:
        client.delete(f"/api/marketplace/listings/{listing_id}")
        console.print(f"[green]Unpublished listing {listing_id[:8]}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

# --- Team/Org commands ---


@marketplace_app.command("search")
def marketplace_search(
    query: str = typer.Argument(..., help="Search query"),
):
    """Search the marketplace."""
    try:
        results = client.get("/api/marketplace/listings", params={"search": query})
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if not results:
        console.print("[dim]No results.[/dim]")
        return

    table = Table(title=f'Marketplace: "{query}"')
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Title", style="bold")
    table.add_column("Category")
    table.add_column("Rating", justify="right")
    table.add_column("Forks", justify="right")

    for item in results:
        table.add_row(
            item["id"][:8],
            item["title"],
            item.get("category", "—"),
            f"{'★' * int(item.get('rating_avg', 0))}" if item.get("rating_avg") else "—",
            str(item.get("fork_count", 0)),
        )
    console.print(table)


def register(parent: typer.Typer) -> None:
    """Forward this module's flat commands and sub-apps onto the root app."""
    for cmd_info in _app.registered_commands:
        parent.registered_commands.append(cmd_info)
    parent.add_typer(marketplace_app, name="marketplace")


