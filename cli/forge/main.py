"""Forge CLI — main entry point.

After the PR-1 split this file just wires the per-workspace command modules.
"""

import typer
from rich.console import Console

from forge import __version__  # re-export
from forge.commands import (
    auth as _auth_mod,
)
from forge.commands import (
    connections as _connections_mod,
)
from forge.commands import (
    evals as _evals_mod,
)
from forge.commands import (
    marketplace as _marketplace_mod,
)
from forge.commands import (
    ops as _ops_mod,
)
from forge.commands import (
    settings as _settings_mod,
)
from forge.commands import (
    studio as _studio_mod,
)
from forge.commands import (
    system as _system_mod,
)

console = Console()

app = typer.Typer(
    name="forge",
    help="Forge CLI — manage and monitor AI agents from the terminal.",
    no_args_is_help=True,
)

for _mod in (
    _system_mod,
    _auth_mod,
    _studio_mod,
    _ops_mod,
    _evals_mod,
    _connections_mod,
    _marketplace_mod,
    _settings_mod,
):
    _mod.register(app)

__all__ = ["app", "console", "__version__"]



# === Unmapped originals retained from main.py ===

def _steer(*args: str) -> dict:
    """Invoke the local steer binary and return its parsed JSON output.

    The CU CLI commands historically posted to /api/blueprints/node-exec, an
    endpoint that does not exist in any router (QA Finding #30). Steer is a
    local binary installed by `scripts/bootstrap-macos.sh`; calling it
    directly is the documented architecture and avoids the round-trip
    entirely.
    """
    import json
    import shutil
    import subprocess

    binary = shutil.which("steer") or str(Path.home() / "bin" / "steer")
    if not Path(binary).exists():
        raise RuntimeError(
            "steer binary not found — run scripts/bootstrap-macos.sh first"
        )
    try:
        result = subprocess.run(
            [binary, *args], capture_output=True, text=True, check=True, timeout=30
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"steer {' '.join(args)} failed: {exc.stderr.strip() or exc.stdout.strip()}"
        ) from exc
    output = (result.stdout or "").strip()
    if not output:
        return {"success": True}
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"success": True, "raw": output}

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
    # Group files by top-level directory component
    dirs: dict[str, list] = {}
    plain_files: list[str] = []

    for f in files:
        path = f.get("path", f) if isinstance(f, dict) else f
        # Strip leading prefix
        rel = path[len(prefix):].lstrip("/") if prefix and path.startswith(prefix) else path
        if "/" in rel:
            top, rest = rel.split("/", 1)
            dirs.setdefault(top, []).append(rest)
        else:
            plain_files.append(rel)

    for d in sorted(dirs.keys()):
        branch = tree.add(f"[bold blue]{d}/[/bold blue]")
        # Rebuild as simple path strings for recursion
        child_files = [{"path": p} for p in dirs[d]]
        _build_file_tree(child_files, branch)

    for f in sorted(plain_files):
        tree.add(f"[green]{f}[/green]")

if __name__ == "__main__":
    app()
