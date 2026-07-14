-- harness-plan.md Phase 5 — real MCP transport columns on mcp_connections.
--
-- Existing rows default to the 'legacy' REST client so nothing breaks; new
-- connections use stdio/http (JSON-RPC 2.0). Additive and idempotent.

ALTER TABLE mcp_connections
    ADD COLUMN IF NOT EXISTS transport  TEXT  NOT NULL DEFAULT 'legacy',
    ADD COLUMN IF NOT EXISTS command    TEXT  NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS args_json  JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS oauth_json JSONB NOT NULL DEFAULT '{}'::jsonb;
