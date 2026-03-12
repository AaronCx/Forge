-- Multi-model provider support
-- Adds model column to agents, provider column to token_usage,
-- and creates provider_configs table for per-user provider credentials.

-- 1. Add model column to agents (default null = use account default)
ALTER TABLE agents ADD COLUMN IF NOT EXISTS model TEXT DEFAULT NULL;

-- 2. Add provider column to token_usage
ALTER TABLE token_usage ADD COLUMN IF NOT EXISTS provider TEXT DEFAULT 'openai';

-- 3. Provider configurations per user (encrypted credentials stored externally)
CREATE TABLE IF NOT EXISTS provider_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    display_name TEXT,
    api_key_encrypted TEXT,  -- encrypted at application layer
    base_url TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, provider)
);

-- RLS for provider_configs
ALTER TABLE provider_configs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage their own provider configs"
    ON provider_configs FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- 4. Add model column to blueprint nodes (stored in JSONB, but add account-level default)
-- Blueprint nodes already store model in their config JSON, so no schema change needed.

-- 5. User preferences for default model
CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE,
    default_model TEXT DEFAULT 'gpt-4o-mini',
    default_provider TEXT DEFAULT 'openai',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage their own preferences"
    ON user_preferences FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- 6. Model comparison runs
CREATE TABLE IF NOT EXISTS comparison_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    prompt TEXT NOT NULL,
    models JSONB NOT NULL,  -- array of model strings
    results JSONB,          -- array of {model, content, tokens, latency_ms, cost}
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE comparison_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage their own comparison runs"
    ON comparison_runs FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
