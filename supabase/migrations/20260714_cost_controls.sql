-- harness-plan.md Phase 7 — per-user cost controls and fallback policy.
-- 0 daily_budget_usd means unlimited. Additive and idempotent.

ALTER TABLE user_preferences
    ADD COLUMN IF NOT EXISTS daily_budget_usd     REAL  NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS fallback_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb;
