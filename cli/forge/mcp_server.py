"""Forge as an MCP server.

Exposes Forge agents and blueprints as MCP tools so any MCP-speaking client
(Claude Code, Claude Desktop, Cursor, …) can invoke Forge orchestrations:

    forge_list_agents       — list the caller's agents
    forge_run_agent         — run an agent, return the aggregated output + run id
    forge_list_blueprints   — list the caller's blueprints
    forge_run_blueprint     — run a blueprint, return the aggregated output + run id
    forge_get_run_status    — fetch a past run's status, output, and step logs

It is a thin adapter over the existing Forge REST API: auth and base-URL
resolution reuse the CLI's config (``~/.forge/config.toml`` /
``FORGE_API_URL`` / ``FORGE_API_KEY``), so authentication is exactly the
``forge login`` session. Transport is stdio by default (what local MCP clients
expect); pass ``--transport sse`` for an HTTP/SSE endpoint.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from forge.config import get_api_key, get_api_url

# Per-call network budgets. Runs stream over SSE and can be long; status/list
# calls are quick.
_RUN_TIMEOUT_S = 600
_QUICK_TIMEOUT_S = 30


class ForgeMCPError(RuntimeError):
    """Raised when the Forge backend is unreachable or rejects a request."""


def _headers() -> dict[str, str]:
    key = get_api_key()
    if not key:
        raise ForgeMCPError(
            "Not authenticated. Run `forge login` (or set FORGE_API_KEY) before "
            "starting the MCP server."
        )
    return {"Authorization": f"Bearer {key}"}


def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{get_api_url()}{path}"
    try:
        r = httpx.get(url, headers=_headers(), params=params, timeout=_QUICK_TIMEOUT_S)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        raise ForgeMCPError(f"{e.response.status_code} from {path}: {e.response.text[:200]}") from e
    except httpx.HTTPError as e:
        raise ForgeMCPError(f"Could not reach Forge at {url}: {e}") from e


def _stream_run(path: str, json_body: dict[str, Any] | None = None,
                params: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST to an SSE run endpoint and aggregate the event stream.

    Returns ``{"run_id", "output", "events"}`` where ``output`` is the
    concatenation of streamed token/text deltas and ``events`` is a compact
    trace (type + short detail) for the model to reason over.
    """
    url = f"{get_api_url()}{path}"
    headers = {**_headers(), "Content-Type": "application/json"}
    output_parts: list[str] = []
    events: list[dict[str, Any]] = []
    run_id: str | None = None

    try:
        with httpx.stream("POST", url, headers=headers, params=params,
                          json=json_body, timeout=_RUN_TIMEOUT_S) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                etype = event.get("type", "")
                payload = event.get("data", "")
                if etype in ("token", "text"):
                    output_parts.append(payload if isinstance(payload, str) else json.dumps(payload))
                elif etype == "result":
                    out = payload.get("output") if isinstance(payload, dict) else None
                    if out:
                        output_parts.append(out if isinstance(out, str) else json.dumps(out))
                    if isinstance(payload, dict) and payload.get("run_id"):
                        run_id = payload["run_id"]
                elif etype == "done":
                    run_id = event.get("run_id", run_id)
                elif etype == "error":
                    raise ForgeMCPError(f"Run failed: {payload}")
                events.append({"type": etype, "detail": _short(payload)})
    except httpx.HTTPStatusError as e:
        raise ForgeMCPError(f"{e.response.status_code} from {path}: {e.response.text[:200]}") from e
    except httpx.HTTPError as e:
        raise ForgeMCPError(f"Could not reach Forge at {url}: {e}") from e

    return {"run_id": run_id, "output": "".join(output_parts), "events": events}


def _short(payload: Any, limit: int = 120) -> str:
    s = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def build_server() -> Any:
    """Construct the FastMCP server with Forge tools registered.

    Imported lazily so the rest of the CLI works without the optional `mcp`
    dependency installed.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:  # pragma: no cover - exercised via CLI error path
        raise ForgeMCPError(
            "The MCP SDK is not installed. Install it with: pip install 'forge-cli[mcp]'"
        ) from e

    mcp = FastMCP("forge")

    @mcp.tool()
    def forge_list_agents() -> list[dict[str, Any]]:
        """List the agents available to the authenticated Forge user.

        Returns each agent's id, name, description, and tool list. Use an
        agent id with forge_run_agent.
        """
        agents = _get("/api/agents")
        return [
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "description": a.get("description", ""),
                "tools": a.get("tools", []),
            }
            for a in (agents or [])
        ]

    @mcp.tool()
    def forge_run_agent(agent_id: str, input_text: str = "") -> dict[str, Any]:
        """Run a Forge agent and return its aggregated output.

        Args:
            agent_id: The agent to run (from forge_list_agents).
            input_text: The prompt/input for the agent.

        Returns the run_id (use with forge_get_run_status) and the agent's
        text output.
        """
        return _stream_run(
            f"/api/agents/{agent_id}/run",
            params={"token": get_api_key(), "input_text": input_text},
        )

    @mcp.tool()
    def forge_list_blueprints() -> list[dict[str, Any]]:
        """List the multi-step blueprints available to the authenticated user.

        Returns each blueprint's id, name, and description. Use a blueprint id
        with forge_run_blueprint.
        """
        bps = _get("/api/blueprints")
        return [
            {
                "id": b.get("id"),
                "name": b.get("name"),
                "description": b.get("description", ""),
            }
            for b in (bps or [])
        ]

    @mcp.tool()
    def forge_run_blueprint(blueprint_id: str, input_text: str = "") -> dict[str, Any]:
        """Run a Forge blueprint (multi-node workflow) and return its output.

        Args:
            blueprint_id: The blueprint to run (from forge_list_blueprints).
            input_text: The input for the blueprint.

        Returns the run_id and the blueprint's aggregated output.
        """
        return _stream_run(
            f"/api/blueprints/{blueprint_id}/run",
            json_body={"input_text": input_text},
        )

    @mcp.tool()
    def forge_get_run_status(run_id: str) -> dict[str, Any]:
        """Fetch the status, output, and step logs of a past Forge run.

        Args:
            run_id: A run id returned by forge_run_agent or forge_run_blueprint.
        """
        run = _get(f"/api/runs/{run_id}")
        return {
            "id": run.get("id"),
            "status": run.get("status"),
            "output": run.get("output"),
            "tokens_used": run.get("tokens_used"),
            "duration_ms": run.get("duration_ms"),
            "step_logs": run.get("step_logs", []),
        }

    return mcp


def serve(transport: str = "stdio") -> None:
    """Run the Forge MCP server on the given transport (`stdio` or `sse`)."""
    if transport not in ("stdio", "sse"):
        raise ForgeMCPError(f"Unknown transport '{transport}'. Use 'stdio' or 'sse'.")
    server = build_server()
    server.run(transport=transport)
