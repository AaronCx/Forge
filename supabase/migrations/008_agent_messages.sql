-- Inter-agent messaging table
CREATE TABLE IF NOT EXISTS agent_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  group_id UUID REFERENCES task_groups(id) ON DELETE CASCADE,
  sender_index INTEGER NOT NULL,
  receiver_index INTEGER,
  message_type TEXT NOT NULL DEFAULT 'info' CHECK (message_type IN ('info', 'request', 'response', 'error', 'handoff')),
  content TEXT NOT NULL,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_agent_messages_group ON agent_messages(group_id);
CREATE INDEX idx_agent_messages_receiver ON agent_messages(group_id, receiver_index);
CREATE INDEX idx_agent_messages_type ON agent_messages(message_type);

-- RLS
ALTER TABLE agent_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view messages in their groups"
  ON agent_messages FOR SELECT
  USING (group_id IN (SELECT id FROM task_groups WHERE user_id = auth.uid()));

CREATE POLICY "Service role manages messages"
  ON agent_messages FOR ALL USING (true) WITH CHECK (true);
