# Forge over MCP (Model Context Protocol)

Forge speaks real MCP (JSON-RPC 2.0) in both directions (harness-plan.md Phase 5):

- **As a client** — connect Forge agents to any MCP server (stdio or Streamable
  HTTP). Discovered tools join the [tool plane](./harness-plan.md) as
  `mcp.<server>.<tool>` and are usable by the native agent loop.
- **As a server** — expose the Forge tool plane (blueprints, nodes, knowledge,
  workspace) to any MCP client such as Claude Code or Codex.

Both directions are gated for safety: the client is behind `FORGE_MCP_V2`; the
server excludes computer-use (`cu.*`) and agent-control (`agent.*`) tools unless
`FORGE_MCP_EXPOSE_CU=1`.

## Forge as an MCP client

Add a server with the CLI:

```bash
# A local stdio server (e.g. the filesystem server)
forge connections mcp add \
  --name filesystem --transport stdio \
  --command npx --arg -y --arg @modelcontextprotocol/server-filesystem --arg /work

# A remote Streamable HTTP server with a bearer token
forge connections mcp add \
  --name remote --transport http --url https://mcp.example.com/mcp --token "$TOKEN"
```

Then enable `FORGE_MCP_V2=1`. The server's tools appear as
`mcp.filesystem.<tool>` in the plane. Outputs are wrapped as untrusted data
(the loop is instructed to treat tool output as data, never as instructions).

## Forge as an MCP server

### Local (stdio) — Claude Code

Add to your Claude Code `.mcp.json`:

```json
{
  "mcpServers": {
    "forge": {
      "command": "forge",
      "args": ["mcp-server"]
    }
  }
}
```

Claude Code will list Forge's blueprints (`blueprint.<slug>`), nodes
(`node.<key>`), knowledge search, and workspace tools, and can call them.

### Codex CLI

Add to your Codex config (`~/.codex/config.toml`):

```toml
[mcp_servers.forge]
command = "forge"
args = ["mcp-server"]
```

### Remote (Streamable HTTP)

`app/mcp/server.py` provides `streamable_http_app(user_id)`, an ASGI app to be
mounted behind the app's existing API-key auth. Point an MCP client's HTTP
transport at the mounted path with an `Authorization: Bearer <api-key>` header.

## Exposing computer use

`cu.*` and `agent.*` tools are excluded from the MCP server by default. To opt
in (only on a trusted host), set `FORGE_MCP_EXPOSE_CU=1` before starting the
server.
