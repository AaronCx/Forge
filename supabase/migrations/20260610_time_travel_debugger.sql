-- Time-travel run debugger
-- Adds an append-only event log for agent runs (run_events) plus a fork lineage
-- table (run_forks). The event log is the source of truth for deterministic
-- replay and edit-and-fork: recording captures every model_call / tool_call /
-- state mutation / step boundary; a fork copies the prefix of these rows up to
-- step N and serves the recorded responses from a cache so unchanged steps are
-- never re-billed.

-- 1. Append-only event log
CREATE TABLE IF NOT EXISTS run_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    step INTEGER NOT NULL DEFAULT 0,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('run_start', 'step_boundary', 'model_call', 'tool_call', 'state', 'run_end')),
    payload JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (run_id, seq)
);

ALTER TABLE run_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view run events for their own runs"
    ON run_events FOR ALL
    USING (run_id IN (SELECT id FROM runs WHERE user_id = auth.uid()))
    WITH CHECK (run_id IN (SELECT id FROM runs WHERE user_id = auth.uid()));

CREATE INDEX IF NOT EXISTS idx_run_events_run_seq ON run_events(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_run_events_run_step ON run_events(run_id, step);

-- 2. Fork lineage
CREATE TABLE IF NOT EXISTS run_forks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    child_run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    from_step INTEGER NOT NULL,
    edits JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE run_forks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage their own run forks"
    ON run_forks FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS idx_run_forks_parent ON run_forks(parent_run_id);
CREATE INDEX IF NOT EXISTS idx_run_forks_child ON run_forks(child_run_id);
CREATE INDEX IF NOT EXISTS idx_run_forks_user ON run_forks(user_id);
