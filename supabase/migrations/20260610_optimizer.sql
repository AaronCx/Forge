-- Eval-driven self-optimization loop (optimizer)
-- Adds optimization_runs (lineage) and optimization_variants tables.
-- An optimization run takes an agent + eval suite, runs a baseline eval, and if
-- there are failures generates N prompt variants, scores each against the suite,
-- selects the winner, and opens an approval to promote it. Nothing is auto-applied.

-- 1. Optimization runs (lineage record)
CREATE TABLE IF NOT EXISTS optimization_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    suite_id UUID NOT NULL REFERENCES eval_suites(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'no_improvement', 'no_failures', 'awaiting_approval', 'failed')),
    parent_prompt TEXT NOT NULL DEFAULT '',
    baseline_run_id UUID REFERENCES eval_runs(id) ON DELETE SET NULL,
    baseline_score REAL,
    winner_variant_id UUID,
    winner_score REAL,
    score_delta REAL,
    approval_id UUID REFERENCES approvals(id) ON DELETE SET NULL,
    summary TEXT DEFAULT '',
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

ALTER TABLE optimization_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage their own optimization runs"
    ON optimization_runs FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- 2. Optimization variants (candidate prompts + per-variant scores)
CREATE TABLE IF NOT EXISTS optimization_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    optimization_run_id UUID NOT NULL REFERENCES optimization_runs(id) ON DELETE CASCADE,
    variant_index INTEGER NOT NULL DEFAULT 0,
    system_prompt TEXT NOT NULL,
    rationale TEXT DEFAULT '',
    eval_run_id UUID REFERENCES eval_runs(id) ON DELETE SET NULL,
    score REAL,
    pass_rate REAL,
    is_winner BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE optimization_variants ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view optimization variants via run"
    ON optimization_variants FOR ALL
    USING (
        optimization_run_id IN (SELECT id FROM optimization_runs WHERE user_id = auth.uid())
    );

-- Indexes
CREATE INDEX IF NOT EXISTS idx_optimization_runs_user ON optimization_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_optimization_runs_agent ON optimization_runs(agent_id);
CREATE INDEX IF NOT EXISTS idx_optimization_variants_run ON optimization_variants(optimization_run_id);
