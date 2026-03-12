-- MCP Integration + Event Triggers (v1.3.0)
-- Adds mcp_connections, triggers, and trigger_history tables.

-- 1. MCP server connections
CREATE TABLE IF NOT EXISTS mcp_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    server_url TEXT NOT NULL,
    status TEXT DEFAULT 'disconnected',
    tools_discovered JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_connected_at TIMESTAMPTZ,
    UNIQUE(user_id, name)
);

ALTER TABLE mcp_connections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage their own MCP connections"
    ON mcp_connections FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- 2. Event triggers
CREATE TABLE IF NOT EXISTS triggers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('webhook', 'cron', 'mcp_event')),
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    target_type TEXT NOT NULL CHECK (target_type IN ('agent', 'blueprint')),
    target_id UUID NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    last_fired_at TIMESTAMPTZ,
    fire_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE triggers ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage their own triggers"
    ON triggers FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- 3. Trigger firing history
CREATE TABLE IF NOT EXISTS trigger_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_id UUID NOT NULL REFERENCES triggers(id) ON DELETE CASCADE,
    payload JSONB DEFAULT '{}'::jsonb,
    run_id UUID,
    status TEXT DEFAULT 'fired',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE trigger_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own trigger history"
    ON trigger_history FOR ALL
    USING (
        trigger_id IN (
            SELECT id FROM triggers WHERE user_id = auth.uid()
        )
    );

-- Index for cron scheduler lookups
CREATE INDEX IF NOT EXISTS idx_triggers_type_enabled ON triggers(type, enabled);

-- Index for trigger history lookups
CREATE INDEX IF NOT EXISTS idx_trigger_history_trigger_id ON trigger_history(trigger_id);
