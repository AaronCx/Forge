-- Eval Framework + Human-in-the-Loop (v1.4.0)
-- Adds eval suites, test cases, eval runs, eval results, and approvals tables.

-- 1. Eval suites
CREATE TABLE IF NOT EXISTS eval_suites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    target_type TEXT NOT NULL CHECK (target_type IN ('agent', 'blueprint')),
    target_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE eval_suites ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage their own eval suites"
    ON eval_suites FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- 2. Eval test cases
CREATE TABLE IF NOT EXISTS eval_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    suite_id UUID NOT NULL REFERENCES eval_suites(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    input JSONB NOT NULL,
    expected_output JSONB,
    grading_method TEXT NOT NULL DEFAULT 'contains'
        CHECK (grading_method IN ('exact_match', 'contains', 'json_schema', 'llm_judge', 'custom', 'human')),
    grading_config JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE eval_cases ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage eval cases via suite"
    ON eval_cases FOR ALL
    USING (
        suite_id IN (SELECT id FROM eval_suites WHERE user_id = auth.uid())
    );

-- 3. Eval runs
CREATE TABLE IF NOT EXISTS eval_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    suite_id UUID NOT NULL REFERENCES eval_suites(id) ON DELETE CASCADE,
    triggered_by TEXT DEFAULT 'manual',
    model_used TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    pass_rate REAL,
    avg_score REAL,
    total_cases INTEGER DEFAULT 0,
    passed_cases INTEGER DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE eval_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage eval runs via suite"
    ON eval_runs FOR ALL
    USING (
        suite_id IN (SELECT id FROM eval_suites WHERE user_id = auth.uid())
    );

-- 4. Eval results (per test case per run)
CREATE TABLE IF NOT EXISTS eval_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    case_id UUID NOT NULL REFERENCES eval_cases(id) ON DELETE CASCADE,
    actual_output JSONB,
    score REAL,
    passed BOOLEAN,
    grading_details JSONB DEFAULT '{}'::jsonb,
    latency_ms INTEGER,
    tokens_used INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE eval_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view eval results via run"
    ON eval_results FOR ALL
    USING (
        run_id IN (
            SELECT id FROM eval_runs WHERE suite_id IN (
                SELECT id FROM eval_suites WHERE user_id = auth.uid()
            )
        )
    );

-- 5. Approvals (human-in-the-loop)
CREATE TABLE IF NOT EXISTS approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    blueprint_run_id UUID NOT NULL,
    node_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    context JSONB DEFAULT '{}'::jsonb,
    feedback TEXT,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE approvals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage their own approvals"
    ON approvals FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_eval_cases_suite ON eval_cases(suite_id);
CREATE INDEX IF NOT EXISTS idx_eval_runs_suite ON eval_runs(suite_id);
CREATE INDEX IF NOT EXISTS idx_eval_results_run ON eval_results(run_id);
CREATE INDEX IF NOT EXISTS idx_approvals_user_status ON approvals(user_id, status);
