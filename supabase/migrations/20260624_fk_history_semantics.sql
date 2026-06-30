-- Align run/cost history FK semantics with the SQLite playbook (§6.4): deleting
-- an agent should PRESERVE its run history and cost records (set agent_id NULL),
-- not cascade-delete them. The original migrations declared these ON DELETE
-- CASCADE, the opposite of the SQLite schema — a silent cross-backend divergence.
-- (agent_heartbeats stays CASCADE — it is transient live state.)

ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_agent_id_fkey;
ALTER TABLE runs ADD CONSTRAINT runs_agent_id_fkey
  FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE SET NULL;

ALTER TABLE token_usage DROP CONSTRAINT IF EXISTS token_usage_agent_id_fkey;
ALTER TABLE token_usage ADD CONSTRAINT token_usage_agent_id_fkey
  FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE SET NULL;
