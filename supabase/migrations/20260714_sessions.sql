-- harness-plan.md Phase 6 — durable sessions and their append-only event log.

CREATE TABLE IF NOT EXISTS sessions (
    id             TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id        UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title          TEXT NOT NULL DEFAULT '',
    model          TEXT NOT NULL DEFAULT '',
    workspace_root TEXT NOT NULL DEFAULT '',
    system_prompt  TEXT NOT NULL DEFAULT '',
    policy_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    token_budget   INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'active',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, updated_at);

CREATE TABLE IF NOT EXISTS session_events (
    id           TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id   TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    seq          INTEGER NOT NULL,
    kind         TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_session_events_session ON session_events(session_id, seq);

ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE session_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role manages sessions" ON sessions;
CREATE POLICY "Service role manages sessions"
    ON sessions FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Users manage own sessions" ON sessions;
CREATE POLICY "Users manage own sessions"
    ON sessions FOR ALL TO authenticated
    USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Service role manages session events" ON session_events;
CREATE POLICY "Service role manages session events"
    ON session_events FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Users read own session events" ON session_events;
CREATE POLICY "Users read own session events"
    ON session_events FOR ALL TO authenticated
    USING (session_id IN (SELECT id FROM sessions WHERE user_id = auth.uid()))
    WITH CHECK (session_id IN (SELECT id FROM sessions WHERE user_id = auth.uid()));
