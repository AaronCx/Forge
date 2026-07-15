-- Phase 9 (dynamic orchestration) — workflow-spawned ephemeral sub-agents.
-- Each compiled SubAgentSpec becomes an agents row (auditable, visible behind
-- a filter, garbage-collectible) tagged with the session that spawned it and
-- the raw spec it was compiled from.

ALTER TABLE agents ADD COLUMN IF NOT EXISTS ephemeral BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS spawned_by_session TEXT DEFAULT NULL;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS spec_json TEXT DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_agents_ephemeral ON agents(user_id, ephemeral);

-- The planner's system template holder is ephemeral too.
UPDATE agents SET ephemeral = true WHERE id LIKE '\_\_planner\_\_%' ESCAPE '\';
