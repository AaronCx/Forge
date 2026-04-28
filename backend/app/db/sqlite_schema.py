"""
SQLite-compatible schema for Forge.

Translated from Supabase/Postgres migrations (001–008, 20260312_*).
All UUIDs are generated in Python (uuid4). Timestamps stored as ISO-8601 TEXT.
JSONB → TEXT (json.dumps). Boolean → INTEGER (0/1). text[] → TEXT (JSON array).
"""

# ---------------------------------------------------------------------------
# 1. Full DDL
# ---------------------------------------------------------------------------
SCHEMA = """\
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ===================== local_users (local auth) =====================
CREATE TABLE IF NOT EXISTS local_users (
    id              TEXT PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ===================== 002_agents =====================
CREATE TABLE IF NOT EXISTS agents (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    name              TEXT NOT NULL,
    description       TEXT DEFAULT '',
    system_prompt     TEXT NOT NULL,
    tools             TEXT DEFAULT '[]',
    workflow_steps    TEXT DEFAULT '[]',
    is_template       INTEGER DEFAULT 0,
    -- 007_hierarchy columns
    parent_agent_id   TEXT REFERENCES agents(id) ON DELETE SET NULL,
    agent_role        TEXT DEFAULT 'worker'
                      CHECK (agent_role IN ('coordinator','supervisor','worker','scout','reviewer')),
    depth             INTEGER DEFAULT 0,
    -- 20260312_blueprints: optional link
    blueprint_id      TEXT REFERENCES blueprints(id) ON DELETE SET NULL,
    -- 20260312_multi_model
    model             TEXT DEFAULT NULL,
    created_at        TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at        TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_agents_user_id     ON agents(user_id);
CREATE INDEX IF NOT EXISTS idx_agents_is_template ON agents(is_template);
CREATE INDEX IF NOT EXISTS idx_agents_parent       ON agents(parent_agent_id);
CREATE INDEX IF NOT EXISTS idx_agents_role         ON agents(agent_role);

-- ===================== 003_runs =====================
CREATE TABLE IF NOT EXISTS runs (
    id             TEXT PRIMARY KEY,
    -- ON DELETE SET NULL preserves run history when the parent agent is deleted
    -- (per QA playbook §6.4 — "don't cascade-delete runs").
    agent_id       TEXT REFERENCES agents(id) ON DELETE SET NULL,
    user_id        TEXT NOT NULL,
    input_text     TEXT,
    input_file_url TEXT,
    output         TEXT,
    step_logs      TEXT DEFAULT '[]',
    status         TEXT DEFAULT 'pending'
                   CHECK (status IN ('pending','running','completed','failed')),
    tokens_used    INTEGER DEFAULT 0,
    duration_ms    INTEGER,
    created_at     TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_runs_user_id    ON runs(user_id);
CREATE INDEX IF NOT EXISTS idx_runs_agent_id   ON runs(agent_id);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at);

-- ===================== 004_api_keys =====================
CREATE TABLE IF NOT EXISTS api_keys (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    key_hash     TEXT NOT NULL,
    name         TEXT NOT NULL,
    last_used_at TEXT,
    created_at   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user_id  ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);

-- ===================== 005_agent_heartbeats =====================
CREATE TABLE IF NOT EXISTS agent_heartbeats (
    id             TEXT PRIMARY KEY,
    agent_id       TEXT NOT NULL REFERENCES agents(id),
    run_id         TEXT REFERENCES runs(id),
    state          TEXT NOT NULL DEFAULT 'idle'
                   CHECK (state IN ('idle','starting','running','stalled','completed','failed')),
    current_step   INTEGER DEFAULT 0,
    total_steps    INTEGER DEFAULT 0,
    tokens_used    INTEGER DEFAULT 0,
    cost_estimate  REAL DEFAULT 0,
    output_preview TEXT DEFAULT '',
    updated_at     TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_at     TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_heartbeats_agent_id   ON agent_heartbeats(agent_id);
CREATE INDEX IF NOT EXISTS idx_heartbeats_run_id     ON agent_heartbeats(run_id);
CREATE INDEX IF NOT EXISTS idx_heartbeats_state      ON agent_heartbeats(state);
CREATE INDEX IF NOT EXISTS idx_heartbeats_updated_at ON agent_heartbeats(updated_at);

-- ===================== 006_token_usage =====================
CREATE TABLE IF NOT EXISTS token_usage (
    id            TEXT PRIMARY KEY,
    run_id        TEXT REFERENCES runs(id),
    agent_id      TEXT REFERENCES agents(id),
    user_id       TEXT NOT NULL,
    step_number   INTEGER NOT NULL DEFAULT 1,
    model         TEXT NOT NULL DEFAULT 'gpt-4o-mini',
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd      REAL NOT NULL DEFAULT 0,
    -- 20260312_multi_model
    provider      TEXT DEFAULT 'openai',
    created_at    TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_token_usage_run_id     ON token_usage(run_id);
CREATE INDEX IF NOT EXISTS idx_token_usage_agent_id   ON token_usage(agent_id);
CREATE INDEX IF NOT EXISTS idx_token_usage_user_id    ON token_usage(user_id);
CREATE INDEX IF NOT EXISTS idx_token_usage_created_at ON token_usage(created_at);
CREATE INDEX IF NOT EXISTS idx_token_usage_model      ON token_usage(model);

-- ===================== 007_hierarchy: task_groups =====================
CREATE TABLE IF NOT EXISTS task_groups (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    objective  TEXT NOT NULL,
    status     TEXT DEFAULT 'pending'
               CHECK (status IN ('pending','planning','running','completed','failed')),
    plan       TEXT DEFAULT '[]',
    result     TEXT,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_task_groups_user   ON task_groups(user_id);
CREATE INDEX IF NOT EXISTS idx_task_groups_status ON task_groups(status);

-- ===================== 007_hierarchy: task_group_members =====================
CREATE TABLE IF NOT EXISTS task_group_members (
    id               TEXT PRIMARY KEY,
    group_id         TEXT NOT NULL REFERENCES task_groups(id),
    agent_id         TEXT REFERENCES agents(id),
    run_id           TEXT REFERENCES runs(id),
    task_description TEXT NOT NULL,
    dependencies     TEXT DEFAULT '[]',
    status           TEXT DEFAULT 'pending'
                     CHECK (status IN ('pending','running','completed','failed')),
    result           TEXT,
    sort_order       INTEGER DEFAULT 0,
    created_at       TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_task_group_members_group ON task_group_members(group_id);

-- ===================== 008_agent_messages =====================
CREATE TABLE IF NOT EXISTS agent_messages (
    id             TEXT PRIMARY KEY,
    group_id       TEXT REFERENCES task_groups(id),
    sender_index   INTEGER NOT NULL,
    receiver_index INTEGER,
    message_type   TEXT NOT NULL DEFAULT 'info'
                   CHECK (message_type IN ('info','request','response','error','handoff')),
    content        TEXT NOT NULL,
    metadata       TEXT DEFAULT '{}',
    created_at     TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_agent_messages_group    ON agent_messages(group_id);
CREATE INDEX IF NOT EXISTS idx_agent_messages_receiver ON agent_messages(group_id, receiver_index);
CREATE INDEX IF NOT EXISTS idx_agent_messages_type     ON agent_messages(message_type);

-- ===================== 20260312_blueprints =====================
CREATE TABLE IF NOT EXISTS blueprints (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    name           TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    version        INTEGER NOT NULL DEFAULT 1,
    is_template    INTEGER NOT NULL DEFAULT 0,
    nodes          TEXT NOT NULL DEFAULT '[]',
    context_config TEXT NOT NULL DEFAULT '{}',
    tool_scope     TEXT NOT NULL DEFAULT '[]',
    retry_policy   TEXT NOT NULL DEFAULT '{"max_retries": 2}',
    output_schema  TEXT,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_blueprints_user_id     ON blueprints(user_id);
CREATE INDEX IF NOT EXISTS idx_blueprints_is_template ON blueprints(is_template);

-- ===================== 20260312_blueprints: blueprint_runs =====================
CREATE TABLE IF NOT EXISTS blueprint_runs (
    id                          TEXT PRIMARY KEY,
    blueprint_id                TEXT NOT NULL REFERENCES blueprints(id),
    user_id                     TEXT NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'pending',
    input_payload               TEXT NOT NULL DEFAULT '{}',
    output                      TEXT,
    execution_trace             TEXT NOT NULL DEFAULT '[]',
    started_at                  TEXT,
    completed_at                TEXT,
    -- 20260312_execution_targets extras
    recording_path              TEXT DEFAULT '',
    recording_duration_seconds  REAL DEFAULT 0,
    recording_size_bytes        INTEGER DEFAULT 0,
    recording_status            TEXT DEFAULT '',
    created_at                  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_blueprint_runs_blueprint_id ON blueprint_runs(blueprint_id);
CREATE INDEX IF NOT EXISTS idx_blueprint_runs_user_id      ON blueprint_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_blueprint_runs_status        ON blueprint_runs(status);

-- ===================== 20260312_computer_use =====================
CREATE TABLE IF NOT EXISTS computer_use_audit_log (
    id              TEXT PRIMARY KEY,
    node_type       TEXT NOT NULL,
    command         TEXT NOT NULL,
    arguments       TEXT DEFAULT '{}',
    target          TEXT DEFAULT '',
    result          TEXT DEFAULT '',
    screenshot_path TEXT,
    user_id         TEXT,
    run_id          TEXT DEFAULT '',
    success         INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_cu_audit_user_time ON computer_use_audit_log(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_cu_audit_run       ON computer_use_audit_log(run_id);

-- ===================== 20260312_eval_hitl: eval_suites =====================
CREATE TABLE IF NOT EXISTS eval_suites (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    target_type TEXT NOT NULL CHECK (target_type IN ('agent','blueprint')),
    target_id   TEXT NOT NULL,
    created_at  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ===================== 20260312_eval_hitl: eval_cases =====================
CREATE TABLE IF NOT EXISTS eval_cases (
    id              TEXT PRIMARY KEY,
    suite_id        TEXT NOT NULL REFERENCES eval_suites(id),
    name            TEXT NOT NULL,
    input           TEXT NOT NULL,
    expected_output TEXT,
    grading_method  TEXT NOT NULL DEFAULT 'contains'
                    CHECK (grading_method IN ('exact_match','contains','json_schema','llm_judge','custom','human')),
    grading_config  TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_eval_cases_suite ON eval_cases(suite_id);

-- ===================== 20260312_eval_hitl: eval_runs =====================
CREATE TABLE IF NOT EXISTS eval_runs (
    id           TEXT PRIMARY KEY,
    suite_id     TEXT NOT NULL REFERENCES eval_suites(id),
    triggered_by TEXT DEFAULT 'manual',
    model_used   TEXT,
    status       TEXT DEFAULT 'pending'
                 CHECK (status IN ('pending','running','completed','failed')),
    pass_rate    REAL,
    avg_score    REAL,
    total_cases  INTEGER DEFAULT 0,
    passed_cases INTEGER DEFAULT 0,
    started_at   TEXT,
    completed_at TEXT,
    created_at   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_eval_runs_suite ON eval_runs(suite_id);

-- ===================== 20260312_eval_hitl: eval_results =====================
CREATE TABLE IF NOT EXISTS eval_results (
    id              TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES eval_runs(id),
    case_id         TEXT NOT NULL REFERENCES eval_cases(id),
    actual_output   TEXT,
    score           REAL,
    passed          INTEGER,
    grading_details TEXT DEFAULT '{}',
    latency_ms      INTEGER,
    tokens_used     INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_eval_results_run ON eval_results(run_id);

-- ===================== 20260312_eval_hitl: approvals =====================
CREATE TABLE IF NOT EXISTS approvals (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    blueprint_run_id TEXT NOT NULL,
    node_id          TEXT NOT NULL,
    status           TEXT DEFAULT 'pending'
                     CHECK (status IN ('pending','approved','rejected')),
    context          TEXT DEFAULT '{}',
    feedback         TEXT,
    decided_at       TEXT,
    created_at       TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_approvals_user_status ON approvals(user_id, status);

-- ===================== 20260312_execution_targets =====================
CREATE TABLE IF NOT EXISTS execution_targets (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    name              TEXT NOT NULL,
    target_type       TEXT NOT NULL DEFAULT 'remote',
    listen_url        TEXT DEFAULT '',
    api_key_encrypted TEXT DEFAULT '',
    platform          TEXT DEFAULT 'macos',
    capabilities      TEXT DEFAULT '{}',
    last_health_check TEXT,
    status            TEXT DEFAULT 'unknown',
    created_at        TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at        TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_exec_targets_user ON execution_targets(user_id);

-- ===================== 20260312_knowledge_rag: knowledge_collections =====================
CREATE TABLE IF NOT EXISTS knowledge_collections (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    embedding_model TEXT DEFAULT 'text-embedding-3-small',
    chunk_size      INTEGER DEFAULT 1000,
    chunk_overlap   INTEGER DEFAULT 200,
    document_count  INTEGER DEFAULT 0,
    chunk_count     INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_knowledge_collections_user ON knowledge_collections(user_id);

-- ===================== 20260312_knowledge_rag: knowledge_documents =====================
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    collection_id TEXT NOT NULL REFERENCES knowledge_collections(id),
    filename      TEXT NOT NULL,
    content_type  TEXT DEFAULT 'text/plain',
    file_size     INTEGER DEFAULT 0,
    raw_text      TEXT DEFAULT '',
    chunk_count   INTEGER DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    metadata      TEXT DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_collection ON knowledge_documents(collection_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_documents_user       ON knowledge_documents(user_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_documents_status     ON knowledge_documents(status);

-- ===================== 20260312_knowledge_rag: knowledge_chunks =====================
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    document_id   TEXT NOT NULL REFERENCES knowledge_documents(id),
    collection_id TEXT NOT NULL REFERENCES knowledge_collections(id),
    chunk_index   INTEGER NOT NULL DEFAULT 0,
    content       TEXT NOT NULL,
    embedding     TEXT,
    token_count   INTEGER DEFAULT 0,
    metadata      TEXT DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document   ON knowledge_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_collection ON knowledge_chunks(collection_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_user       ON knowledge_chunks(user_id);

-- ===================== 20260312_marketplace_teams: organizations =====================
CREATE TABLE IF NOT EXISTS organizations (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    owner_id    TEXT NOT NULL,
    avatar_url  TEXT DEFAULT '',
    settings    TEXT DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_organizations_owner ON organizations(owner_id);

-- ===================== 20260312_marketplace_teams: org_members =====================
CREATE TABLE IF NOT EXISTS org_members (
    id         TEXT PRIMARY KEY,
    org_id     TEXT NOT NULL REFERENCES organizations(id),
    user_id    TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'member',
    invited_by TEXT,
    joined_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(org_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_org_members_org  ON org_members(org_id);
CREATE INDEX IF NOT EXISTS idx_org_members_user ON org_members(user_id);

-- ===================== 20260312_marketplace_teams: marketplace_listings =====================
CREATE TABLE IF NOT EXISTS marketplace_listings (
    id            TEXT PRIMARY KEY,
    blueprint_id  TEXT NOT NULL REFERENCES blueprints(id),
    user_id       TEXT NOT NULL,
    org_id        TEXT REFERENCES organizations(id),
    title         TEXT NOT NULL,
    description   TEXT DEFAULT '',
    category      TEXT DEFAULT 'general',
    tags          TEXT DEFAULT '[]',
    version       TEXT DEFAULT '1.0.0',
    status        TEXT NOT NULL DEFAULT 'published',
    fork_count    INTEGER DEFAULT 0,
    rating_avg    REAL DEFAULT 0,
    rating_count  INTEGER DEFAULT 0,
    install_count INTEGER DEFAULT 0,
    metadata      TEXT DEFAULT '{}',
    published_at  TEXT,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_marketplace_user     ON marketplace_listings(user_id);
CREATE INDEX IF NOT EXISTS idx_marketplace_status   ON marketplace_listings(status);
CREATE INDEX IF NOT EXISTS idx_marketplace_category ON marketplace_listings(category);
CREATE INDEX IF NOT EXISTS idx_marketplace_rating   ON marketplace_listings(rating_avg);

-- ===================== 20260312_marketplace_teams: marketplace_ratings =====================
CREATE TABLE IF NOT EXISTS marketplace_ratings (
    id         TEXT PRIMARY KEY,
    listing_id TEXT NOT NULL REFERENCES marketplace_listings(id),
    user_id    TEXT NOT NULL,
    rating     INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    review     TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(listing_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_ratings_listing ON marketplace_ratings(listing_id);

-- ===================== 20260312_marketplace_teams: marketplace_forks =====================
CREATE TABLE IF NOT EXISTS marketplace_forks (
    id                   TEXT PRIMARY KEY,
    listing_id           TEXT NOT NULL REFERENCES marketplace_listings(id),
    source_blueprint_id  TEXT NOT NULL REFERENCES blueprints(id),
    forked_blueprint_id  TEXT NOT NULL REFERENCES blueprints(id),
    user_id              TEXT NOT NULL,
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_forks_listing ON marketplace_forks(listing_id);
CREATE INDEX IF NOT EXISTS idx_forks_user    ON marketplace_forks(user_id);

-- ===================== 20260312_mcp_triggers: mcp_connections =====================
CREATE TABLE IF NOT EXISTS mcp_connections (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    name              TEXT NOT NULL,
    server_url        TEXT NOT NULL,
    status            TEXT DEFAULT 'disconnected',
    tools_discovered  TEXT DEFAULT '[]',
    created_at        TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_connected_at TEXT,
    UNIQUE(user_id, name)
);

-- ===================== 20260312_mcp_triggers: triggers =====================
CREATE TABLE IF NOT EXISTS triggers (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    type          TEXT NOT NULL CHECK (type IN ('webhook','cron','mcp_event')),
    config        TEXT NOT NULL DEFAULT '{}',
    target_type   TEXT NOT NULL CHECK (target_type IN ('agent','blueprint')),
    target_id     TEXT NOT NULL,
    enabled       INTEGER DEFAULT 1,
    last_fired_at TEXT,
    fire_count    INTEGER DEFAULT 0,
    created_at    TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_triggers_type_enabled ON triggers(type, enabled);

-- ===================== 20260312_mcp_triggers: trigger_history =====================
CREATE TABLE IF NOT EXISTS trigger_history (
    id         TEXT PRIMARY KEY,
    trigger_id TEXT NOT NULL REFERENCES triggers(id),
    payload    TEXT DEFAULT '{}',
    run_id     TEXT,
    status     TEXT DEFAULT 'fired',
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_trigger_history_trigger_id ON trigger_history(trigger_id);

-- ===================== 20260312_multi_model: provider_configs =====================
CREATE TABLE IF NOT EXISTS provider_configs (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    provider          TEXT NOT NULL,
    display_name      TEXT,
    api_key_encrypted TEXT,
    base_url          TEXT,
    is_default        INTEGER DEFAULT 0,
    is_enabled        INTEGER DEFAULT 1,
    created_at        TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at        TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(user_id, provider)
);

-- ===================== 20260312_multi_model: user_preferences =====================
CREATE TABLE IF NOT EXISTS user_preferences (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL UNIQUE,
    default_model    TEXT DEFAULT 'gpt-4o-mini',
    default_provider TEXT DEFAULT 'openai',
    created_at       TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at       TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ===================== 20260312_multi_model: comparison_runs =====================
CREATE TABLE IF NOT EXISTS comparison_runs (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    prompt     TEXT NOT NULL,
    models     TEXT NOT NULL,
    results    TEXT,
    status     TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ===================== 20260312_observability_prompts: traces =====================
CREATE TABLE IF NOT EXISTS traces (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    run_id           TEXT REFERENCES runs(id),
    blueprint_run_id TEXT REFERENCES blueprint_runs(id),
    agent_id         TEXT REFERENCES agents(id),
    span_type        TEXT NOT NULL DEFAULT 'llm_call',
    span_name        TEXT NOT NULL DEFAULT '',
    parent_span_id   TEXT REFERENCES traces(id),
    model            TEXT,
    provider         TEXT,
    input_tokens     INTEGER DEFAULT 0,
    output_tokens    INTEGER DEFAULT 0,
    latency_ms       REAL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'ok',
    input_preview    TEXT DEFAULT '',
    output_preview   TEXT DEFAULT '',
    error_message    TEXT,
    metadata         TEXT DEFAULT '{}',
    started_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ended_at         TEXT,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_traces_user_id          ON traces(user_id);
CREATE INDEX IF NOT EXISTS idx_traces_run_id           ON traces(run_id);
CREATE INDEX IF NOT EXISTS idx_traces_blueprint_run_id ON traces(blueprint_run_id);
CREATE INDEX IF NOT EXISTS idx_traces_agent_id         ON traces(agent_id);
CREATE INDEX IF NOT EXISTS idx_traces_parent_span_id   ON traces(parent_span_id);
CREATE INDEX IF NOT EXISTS idx_traces_created_at       ON traces(created_at);
CREATE INDEX IF NOT EXISTS idx_traces_span_type        ON traces(span_type);

-- ===================== 20260312_observability_prompts: prompt_versions =====================
CREATE TABLE IF NOT EXISTS prompt_versions (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL,
    agent_id            TEXT REFERENCES agents(id),
    version_number      INTEGER NOT NULL DEFAULT 1,
    system_prompt       TEXT NOT NULL,
    change_summary      TEXT DEFAULT '',
    diff_from_previous  TEXT DEFAULT '',
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_prompt_versions_agent  ON prompt_versions(agent_id, version_number);
CREATE INDEX IF NOT EXISTS idx_prompt_versions_user   ON prompt_versions(user_id);
CREATE INDEX IF NOT EXISTS idx_prompt_versions_active ON prompt_versions(agent_id, is_active);

-- ===================== workspaces =====================
CREATE TABLE IF NOT EXISTS workspaces (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    path            TEXT NOT NULL,
    status          TEXT DEFAULT 'active' CHECK (status IN ('active','archived','deleted')),
    settings        TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_workspaces_user   ON workspaces(user_id);
CREATE INDEX IF NOT EXISTS idx_workspaces_name   ON workspaces(user_id, name);

-- ===================== workspace_changes =====================
CREATE TABLE IF NOT EXISTS workspace_changes (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    file_path       TEXT NOT NULL,
    change_type     TEXT NOT NULL CHECK (change_type IN ('create','modify','delete','rename')),
    content_before  TEXT,
    content_after   TEXT,
    attribution     TEXT DEFAULT 'user:web',
    created_at      TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_ws_changes_workspace ON workspace_changes(workspace_id);
CREATE INDEX IF NOT EXISTS idx_ws_changes_file      ON workspace_changes(workspace_id, file_path);
CREATE INDEX IF NOT EXISTS idx_ws_changes_time      ON workspace_changes(created_at);
"""

# ---------------------------------------------------------------------------
# 2. Columns that hold JSON-serialized data (need json.loads on read,
#    json.dumps on write).
# ---------------------------------------------------------------------------
JSON_COLUMNS: dict[str, set[str]] = {
    "agents":                  {"tools", "workflow_steps"},
    "runs":                    {"step_logs"},
    "agent_messages":          {"metadata"},
    "task_groups":             {"plan"},
    "task_group_members":      {"dependencies"},
    "blueprints":              {"nodes", "context_config", "tool_scope", "retry_policy", "output_schema"},
    "blueprint_runs":          {"input_payload", "output", "execution_trace"},
    "computer_use_audit_log":  {"arguments"},
    "eval_cases":              {"input", "expected_output", "grading_config"},
    "eval_results":            {"actual_output", "grading_details"},
    "approvals":               {"context"},
    "execution_targets":       {"capabilities"},
    "knowledge_documents":     {"metadata"},
    "knowledge_chunks":        {"embedding", "metadata"},
    "organizations":           {"settings"},
    "marketplace_listings":    {"tags", "metadata"},
    "mcp_connections":         {"tools_discovered"},
    "triggers":                {"config"},
    "trigger_history":         {"payload"},
    "comparison_runs":         {"models", "results"},
    "traces":                  {"metadata"},
    "workspaces":              {"settings"},
}

# ---------------------------------------------------------------------------
# 3. Foreign-key map: (source_table, target_table) → (source_col, target_col)
#    Captures every FK declared across the schema. Where a table has multiple
#    FKs to the same target, entries are keyed with a distinguishing tuple.
# ---------------------------------------------------------------------------
FK_MAP: dict[tuple[str, str], tuple[str, str]] = {
    # 003 runs
    ("runs", "agents"):                          ("agent_id", "id"),
    # 005 heartbeats
    ("agent_heartbeats", "agents"):              ("agent_id", "id"),
    ("agent_heartbeats", "runs"):                ("run_id", "id"),
    # 006 token_usage
    ("token_usage", "runs"):                     ("run_id", "id"),
    ("token_usage", "agents"):                   ("agent_id", "id"),
    # 007 hierarchy
    ("agents", "agents"):                        ("parent_agent_id", "id"),
    ("task_group_members", "task_groups"):        ("group_id", "id"),
    ("task_group_members", "agents"):             ("agent_id", "id"),
    ("task_group_members", "runs"):               ("run_id", "id"),
    # 008 agent_messages
    ("agent_messages", "task_groups"):            ("group_id", "id"),
    # blueprints
    ("agents", "blueprints"):                    ("blueprint_id", "id"),
    ("blueprint_runs", "blueprints"):            ("blueprint_id", "id"),
    # eval
    ("eval_cases", "eval_suites"):               ("suite_id", "id"),
    ("eval_runs", "eval_suites"):                ("suite_id", "id"),
    ("eval_results", "eval_runs"):               ("run_id", "id"),
    ("eval_results", "eval_cases"):              ("case_id", "id"),
    # marketplace
    ("marketplace_listings", "blueprints"):      ("blueprint_id", "id"),
    ("marketplace_listings", "organizations"):   ("org_id", "id"),
    ("marketplace_ratings", "marketplace_listings"): ("listing_id", "id"),
    ("marketplace_forks", "marketplace_listings"):   ("listing_id", "id"),
    # org_members
    ("org_members", "organizations"):            ("org_id", "id"),
    # mcp / triggers
    ("trigger_history", "triggers"):             ("trigger_id", "id"),
    # knowledge
    ("knowledge_documents", "knowledge_collections"): ("collection_id", "id"),
    ("knowledge_chunks", "knowledge_documents"):      ("document_id", "id"),
    ("knowledge_chunks", "knowledge_collections"):    ("collection_id", "id"),
    # traces
    ("traces", "runs"):                          ("run_id", "id"),
    ("traces", "blueprint_runs"):                ("blueprint_run_id", "id"),
    ("traces", "agents"):                        ("agent_id", "id"),
    ("traces", "traces"):                        ("parent_span_id", "id"),
    # prompt_versions
    ("prompt_versions", "agents"):               ("agent_id", "id"),
    # marketplace_forks → blueprints (two FKs, use source_blueprint_id as primary entry)
    # Note: marketplace_forks has source_blueprint_id AND forked_blueprint_id → blueprints
    # Only one key per (src, tgt) pair is possible; store the first.
    ("marketplace_forks", "blueprints"):         ("source_blueprint_id", "id"),
    # workspaces
    ("workspace_changes", "workspaces"):         ("workspace_id", "id"),
}
