-- forge-onboarding-spec — first-login onboarding + per-user tailoring
-- Adds onboarding state to user_preferences.

ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS onboarded_at TIMESTAMPTZ;
ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS use_case TEXT;
ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS custom_instructions TEXT;
