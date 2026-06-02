-- forge-onboarding-spec (PR-6) — dashboard getting-started checklist dismissal.

ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS getting_started_dismissed BOOLEAN DEFAULT FALSE;
