CREATE TABLE IF NOT EXISTS agent_heartbeats (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  run_id UUID REFERENCES runs(id) ON DELETE CASCADE,
  state TEXT NOT NULL DEFAULT 'idle' CHECK (state IN ('idle', 'starting', 'running', 'stalled', 'completed', 'failed')),
  current_step INTEGER DEFAULT 0,
  total_steps INTEGER DEFAULT 0,
  tokens_used INTEGER DEFAULT 0,
  cost_estimate NUMERIC(10, 6) DEFAULT 0,
  output_preview TEXT DEFAULT '',
  updated_at TIMESTAMPTZ DEFAULT now(),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_heartbeats_agent_id ON agent_heartbeats(agent_id);
CREATE INDEX idx_heartbeats_run_id ON agent_heartbeats(run_id);
CREATE INDEX idx_heartbeats_state ON agent_heartbeats(state);
CREATE INDEX idx_heartbeats_updated_at ON agent_heartbeats(updated_at DESC);

-- Trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_heartbeat_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER heartbeat_updated_at
  BEFORE UPDATE ON agent_heartbeats
  FOR EACH ROW
  EXECUTE FUNCTION update_heartbeat_timestamp();

-- RLS policies
ALTER TABLE agent_heartbeats ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view heartbeats for their agents"
  ON agent_heartbeats FOR SELECT
  USING (
    agent_id IN (SELECT id FROM agents WHERE user_id = auth.uid())
  );

CREATE POLICY "Service role can manage heartbeats"
  ON agent_heartbeats FOR ALL
  USING (true)
  WITH CHECK (true);
