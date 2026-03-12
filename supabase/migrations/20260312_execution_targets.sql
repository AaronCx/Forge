-- Execution targets for multi-machine dispatch
CREATE TABLE IF NOT EXISTS execution_targets (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id uuid REFERENCES auth.users(id) NOT NULL,
    name text NOT NULL,
    target_type text NOT NULL DEFAULT 'remote',
    listen_url text DEFAULT '',
    api_key_encrypted text DEFAULT '',
    platform text DEFAULT 'macos',
    capabilities jsonb DEFAULT '{}',
    last_health_check timestamptz,
    status text DEFAULT 'unknown',
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- Index for querying by user
CREATE INDEX IF NOT EXISTS idx_exec_targets_user
    ON execution_targets(user_id);

-- RLS policies
ALTER TABLE execution_targets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own targets"
    ON execution_targets FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own targets"
    ON execution_targets FOR ALL
    USING (auth.uid() = user_id);

-- Recording metadata columns on blueprint_runs (if table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'blueprint_runs') THEN
        ALTER TABLE blueprint_runs ADD COLUMN IF NOT EXISTS recording_path text DEFAULT '';
        ALTER TABLE blueprint_runs ADD COLUMN IF NOT EXISTS recording_duration_seconds float DEFAULT 0;
        ALTER TABLE blueprint_runs ADD COLUMN IF NOT EXISTS recording_size_bytes bigint DEFAULT 0;
        ALTER TABLE blueprint_runs ADD COLUMN IF NOT EXISTS recording_status text DEFAULT '';
    END IF;
END $$;
