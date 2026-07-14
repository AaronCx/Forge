-- harness-plan.md Phase 3 — per-user tool-plane permission policies.
--
-- Stores allow/ask/deny decisions per (user, tool). Absence of a row falls back
-- to the tool's danger_level default. Additive; owner-scoped RLS mirrors the
-- other per-user tables.

CREATE TABLE IF NOT EXISTS tool_policies (
    id         TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tool_name  TEXT NOT NULL,
    decision   TEXT NOT NULL DEFAULT 'ask'
               CHECK (decision IN ('allow', 'ask', 'deny')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, tool_name)
);

CREATE INDEX IF NOT EXISTS idx_tool_policies_user ON tool_policies(user_id);

ALTER TABLE tool_policies ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role manages tool policies" ON tool_policies;
CREATE POLICY "Service role manages tool policies"
    ON tool_policies FOR ALL
    TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Users manage own tool policies" ON tool_policies;
CREATE POLICY "Users manage own tool policies"
    ON tool_policies FOR ALL
    TO authenticated
    USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
