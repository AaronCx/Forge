-- v1.5.0: Observability Traces + Prompt Versioning
-- Traces table for detailed execution event logging
-- Prompt versions table for system prompt history and rollback

-- ========================================
-- Traces
-- ========================================
CREATE TABLE IF NOT EXISTS traces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    run_id UUID REFERENCES runs(id) ON DELETE SET NULL,
    blueprint_run_id UUID REFERENCES blueprint_runs(id) ON DELETE SET NULL,
    agent_id UUID REFERENCES agents(id) ON DELETE SET NULL,
    span_type TEXT NOT NULL DEFAULT 'llm_call',
    -- span_type: llm_call, tool_call, node_execution, agent_step, blueprint_step
    span_name TEXT NOT NULL DEFAULT '',
    parent_span_id UUID REFERENCES traces(id) ON DELETE SET NULL,
    model TEXT,
    provider TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    latency_ms REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ok',
    -- status: ok, error, timeout
    input_preview TEXT DEFAULT '',
    output_preview TEXT DEFAULT '',
    error_message TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_traces_user_id ON traces(user_id);
CREATE INDEX idx_traces_run_id ON traces(run_id);
CREATE INDEX idx_traces_blueprint_run_id ON traces(blueprint_run_id);
CREATE INDEX idx_traces_agent_id ON traces(agent_id);
CREATE INDEX idx_traces_parent_span_id ON traces(parent_span_id);
CREATE INDEX idx_traces_created_at ON traces(created_at DESC);
CREATE INDEX idx_traces_span_type ON traces(span_type);

ALTER TABLE traces ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own traces"
    ON traces FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own traces"
    ON traces FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- ========================================
-- Prompt Versions
-- ========================================
CREATE TABLE IF NOT EXISTS prompt_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL DEFAULT 1,
    system_prompt TEXT NOT NULL,
    change_summary TEXT DEFAULT '',
    -- Stores the diff from previous version as text
    diff_from_previous TEXT DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_prompt_versions_agent ON prompt_versions(agent_id, version_number DESC);
CREATE INDEX idx_prompt_versions_user ON prompt_versions(user_id);
CREATE INDEX idx_prompt_versions_active ON prompt_versions(agent_id, is_active) WHERE is_active = true;

ALTER TABLE prompt_versions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own prompt versions"
    ON prompt_versions FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own prompt versions"
    ON prompt_versions FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own prompt versions"
    ON prompt_versions FOR UPDATE
    USING (auth.uid() = user_id);
