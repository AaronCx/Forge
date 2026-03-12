-- Computer use audit log for tracking all GUI and terminal actions
CREATE TABLE IF NOT EXISTS computer_use_audit_log (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    node_type text NOT NULL,
    command text NOT NULL,
    arguments jsonb DEFAULT '{}',
    target text DEFAULT '',
    result text DEFAULT '',
    screenshot_path text,
    user_id uuid REFERENCES auth.users(id),
    run_id text DEFAULT '',
    success boolean DEFAULT true,
    created_at timestamptz DEFAULT now()
);

-- Index for querying by user and time
CREATE INDEX IF NOT EXISTS idx_cu_audit_user_time
    ON computer_use_audit_log(user_id, created_at DESC);

-- Index for querying by run
CREATE INDEX IF NOT EXISTS idx_cu_audit_run
    ON computer_use_audit_log(run_id)
    WHERE run_id != '';

-- RLS policies
ALTER TABLE computer_use_audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own audit logs"
    ON computer_use_audit_log FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role can insert audit logs"
    ON computer_use_audit_log FOR INSERT
    WITH CHECK (true);
