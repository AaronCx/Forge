-- harness-plan.md Phase 1 — per-user model card overrides.
--
-- Adds a JSONB column to provider_configs holding a per-user array of partial
-- or full ModelCard dicts that are merged over the bundled
-- backend/app/kernel/models.json at load time. Additive and idempotent; no RLS
-- change (the existing provider_configs owner policy already covers the row).

ALTER TABLE provider_configs
    ADD COLUMN IF NOT EXISTS model_overrides JSONB NOT NULL DEFAULT '[]'::jsonb;
