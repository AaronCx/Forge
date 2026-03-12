-- Add hierarchy columns to agents
ALTER TABLE agents ADD COLUMN IF NOT EXISTS parent_agent_id UUID REFERENCES agents(id) ON DELETE SET NULL;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS agent_role TEXT DEFAULT 'worker' CHECK (agent_role IN ('coordinator', 'supervisor', 'worker', 'scout', 'reviewer'));
ALTER TABLE agents ADD COLUMN IF NOT EXISTS depth INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_agents_parent ON agents(parent_agent_id);
CREATE INDEX IF NOT EXISTS idx_agents_role ON agents(agent_role);

-- Task groups for batch coordination
CREATE TABLE IF NOT EXISTS task_groups (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  objective TEXT NOT NULL,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'planning', 'running', 'completed', 'failed')),
  plan JSONB DEFAULT '[]',
  result TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS task_group_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  group_id UUID NOT NULL REFERENCES task_groups(id) ON DELETE CASCADE,
  agent_id UUID REFERENCES agents(id) ON DELETE SET NULL,
  run_id UUID REFERENCES runs(id) ON DELETE SET NULL,
  task_description TEXT NOT NULL,
  dependencies JSONB DEFAULT '[]',
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
  result TEXT,
  sort_order INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_task_groups_user ON task_groups(user_id);
CREATE INDEX idx_task_groups_status ON task_groups(status);
CREATE INDEX idx_task_group_members_group ON task_group_members(group_id);

-- RLS
ALTER TABLE task_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_group_members ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their task groups"
  ON task_groups FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can manage their task groups"
  ON task_groups FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can view members of their groups"
  ON task_group_members FOR SELECT
  USING (group_id IN (SELECT id FROM task_groups WHERE user_id = auth.uid()));
CREATE POLICY "Service role manages members"
  ON task_group_members FOR ALL USING (true) WITH CHECK (true);

-- Trigger for task_groups updated_at
CREATE TRIGGER task_groups_updated_at
  BEFORE UPDATE ON task_groups
  FOR EACH ROW
  EXECUTE FUNCTION update_heartbeat_timestamp();
