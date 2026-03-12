import { API_URL } from "@/lib/constants";

interface RequestOptions extends RequestInit {
  token?: string;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { token, ...fetchOptions } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}${path}`, { ...fetchOptions, headers });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || "Request failed");
  }

  return res.json();
}

export interface Agent {
  id: string;
  user_id: string;
  name: string;
  description: string;
  system_prompt: string;
  tools: string[];
  workflow_steps: string[];
  model: string | null;
  is_template: boolean;
  created_at: string;
  updated_at: string;
}

export interface Run {
  id: string;
  agent_id: string;
  user_id: string;
  input_text: string | null;
  input_file_url: string | null;
  output: string | null;
  step_logs: { step: number; result: string; duration_ms: number }[];
  status: "pending" | "running" | "completed" | "failed";
  tokens_used: number;
  duration_ms: number | null;
  created_at: string;
}

export interface AgentCreate {
  name: string;
  description: string;
  system_prompt: string;
  tools: string[];
  workflow_steps: string[];
  model?: string | null;
}

export interface ProviderInfo {
  providers: string[];
  default_model: string;
  default_provider: string | null;
}

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  context_window: number | null;
  max_output_tokens: number | null;
  supports_tools: boolean;
  supports_streaming: boolean;
}

export interface ProviderHealthInfo {
  provider: string;
  status: "healthy" | "degraded" | "unavailable";
  latency_ms: number | null;
  error: string | null;
}

export interface CompareResult {
  model: string;
  provider: string;
  content: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  cost: number;
  error: string | null;
}

export interface CompareResponse {
  id: string;
  results: CompareResult[];
}

export interface BlueprintNode {
  id: string;
  type: string;
  label: string;
  config: Record<string, unknown>;
  dependencies: string[];
  position?: { x: number; y: number };
}

export interface Blueprint {
  id: string;
  user_id: string;
  name: string;
  description: string;
  version: number;
  is_template: boolean;
  nodes: BlueprintNode[];
  context_config: Record<string, unknown>;
  tool_scope: string[];
  retry_policy: { max_retries: number };
  output_schema: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface BlueprintRun {
  id: string;
  blueprint_id: string;
  user_id: string;
  status: string;
  input_payload: Record<string, unknown>;
  output: Record<string, unknown> | null;
  execution_trace: Record<string, unknown>[];
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface NodeTypeInfo {
  key: string;
  display_name: string;
  category: string;
  node_class: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
}

export interface MCPConnection {
  id: string;
  name: string;
  server_url: string;
  status: string;
  tools_discovered: { name: string; description: string; input_schema: Record<string, unknown> }[];
  created_at: string;
  last_connected_at: string | null;
}

export interface MCPTool {
  name: string;
  display_name: string;
  description: string;
  source: string;
  source_id: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
}

export interface Trigger {
  id: string;
  user_id: string;
  type: "webhook" | "cron" | "mcp_event";
  config: Record<string, unknown>;
  target_type: "agent" | "blueprint";
  target_id: string;
  enabled: boolean;
  last_fired_at: string | null;
  fire_count: number;
  created_at: string;
}

export interface TriggerHistory {
  id: string;
  trigger_id: string;
  payload: Record<string, unknown>;
  run_id: string | null;
  status: string;
  created_at: string;
}

export interface EvalSuite {
  id: string;
  user_id: string;
  name: string;
  description: string;
  target_type: "agent" | "blueprint";
  target_id: string;
  created_at: string;
  cases?: EvalCase[];
}

export interface EvalCase {
  id: string;
  suite_id: string;
  name: string;
  input: Record<string, unknown>;
  expected_output: Record<string, unknown> | null;
  grading_method: string;
  grading_config: Record<string, unknown>;
  created_at: string;
}

export interface EvalRun {
  id: string;
  suite_id: string;
  triggered_by: string;
  model_used: string | null;
  status: string;
  pass_rate: number | null;
  avg_score: number | null;
  total_cases: number;
  passed_cases: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  results?: EvalResult[];
}

export interface EvalResult {
  id: string;
  run_id: string;
  case_id: string;
  actual_output: Record<string, unknown> | null;
  score: number | null;
  passed: boolean | null;
  grading_details: Record<string, unknown>;
  latency_ms: number | null;
  tokens_used: number;
}

export interface Approval {
  id: string;
  user_id: string;
  blueprint_run_id: string;
  node_id: string;
  status: "pending" | "approved" | "rejected";
  context: Record<string, unknown>;
  feedback: string | null;
  decided_at: string | null;
  created_at: string;
}

export const api = {
  agents: {
    list: (token: string) => request<Agent[]>("/api/agents", { token }),
    get: (id: string, token: string) => request<Agent>(`/api/agents/${id}`, { token }),
    create: (data: AgentCreate, token: string) =>
      request<Agent>("/api/agents", { method: "POST", body: JSON.stringify(data), token }),
    update: (id: string, data: Partial<AgentCreate>, token: string) =>
      request<Agent>(`/api/agents/${id}`, { method: "PUT", body: JSON.stringify(data), token }),
    delete: (id: string, token: string) =>
      request<void>(`/api/agents/${id}`, { method: "DELETE", token }),
    templates: (token: string) => request<Agent[]>("/api/agents/templates", { token }),
  },
  runs: {
    list: (token: string) => request<Run[]>("/api/runs", { token }),
    get: (id: string, token: string) => request<Run>(`/api/runs/${id}`, { token }),
    start: (agentId: string, input: { text?: string; file_url?: string }, token: string) => {
      return `${API_URL}/api/agents/${agentId}/run?token=${encodeURIComponent(token)}&input_text=${encodeURIComponent(input.text || "")}`;
    },
  },
  keys: {
    list: (token: string) => request<{ id: string; name: string; created_at: string; last_used_at: string | null }[]>("/api/keys", { token }),
    create: (name: string, token: string) =>
      request<{ key: string }>("/api/keys", { method: "POST", body: JSON.stringify({ name }), token }),
    delete: (id: string, token: string) =>
      request<void>(`/api/keys/${id}`, { method: "DELETE", token }),
  },
  stats: {
    get: (token: string) =>
      request<{ total_runs: number; total_tokens: number; total_agents: number; runs_this_hour: number }>("/api/stats", { token }),
  },
  blueprints: {
    list: (token: string) => request<Blueprint[]>("/api/blueprints", { token }),
    get: (id: string, token: string) => request<Blueprint>(`/api/blueprints/${id}`, { token }),
    create: (data: { name: string; description: string; nodes: BlueprintNode[]; context_config?: Record<string, unknown>; tool_scope?: string[]; retry_policy?: { max_retries: number } }, token: string) =>
      request<Blueprint>("/api/blueprints", { method: "POST", body: JSON.stringify(data), token }),
    update: (id: string, data: Partial<Blueprint>, token: string) =>
      request<Blueprint>(`/api/blueprints/${id}`, { method: "PUT", body: JSON.stringify(data), token }),
    delete: (id: string, token: string) =>
      request<void>(`/api/blueprints/${id}`, { method: "DELETE", token }),
    templates: () => request<Blueprint[]>("/api/blueprints/templates"),
    nodeTypes: () => request<NodeTypeInfo[]>("/api/blueprints/node-types"),
    run: (id: string) =>
      `${API_URL}/api/blueprints/${id}/run`,
    getRun: (runId: string, token: string) => request<BlueprintRun>(`/api/blueprints/runs/${runId}`, { token }),
    listRuns: (id: string, token: string) => request<BlueprintRun[]>(`/api/blueprints/${id}/runs`, { token }),
  },
  providers: {
    list: (token: string) => request<ProviderInfo>("/api/providers", { token }),
    models: (token: string) => request<ModelInfo[]>("/api/providers/models", { token }),
    providerModels: (provider: string, token: string) =>
      request<ModelInfo[]>(`/api/providers/models/${provider}`, { token }),
    health: (token: string) => request<ProviderHealthInfo[]>("/api/providers/health", { token }),
  },
  compare: {
    run: (data: { prompt: string; system_prompt?: string; models: string[]; temperature?: number; max_tokens?: number }, token: string) =>
      request<CompareResponse>("/api/compare", { method: "POST", body: JSON.stringify(data), token }),
    get: (id: string, token: string) => request<CompareResponse>(`/api/compare/${id}`, { token }),
  },
  mcp: {
    connect: (data: { name: string; server_url: string }, token: string) =>
      request<MCPConnection>("/api/mcp/connect", { method: "POST", body: JSON.stringify(data), token }),
    connections: (token: string) => request<MCPConnection[]>("/api/mcp/connections", { token }),
    deleteConnection: (id: string, token: string) =>
      request<void>(`/api/mcp/connections/${id}`, { method: "DELETE", token }),
    connectionTools: (id: string, token: string) =>
      request<MCPConnection["tools_discovered"]>(`/api/mcp/connections/${id}/tools`, { token }),
    testConnection: (id: string, token: string) =>
      request<{ status: string; latency_ms: number | null; error: string | null }>(`/api/mcp/connections/${id}/test`, { method: "POST", token }),
    tools: (token: string) => request<MCPTool[]>("/api/tools", { token }),
  },
  evals: {
    suites: (token: string) => request<EvalSuite[]>("/api/evals/suites", { token }),
    getSuite: (id: string, token: string) => request<EvalSuite>(`/api/evals/suites/${id}`, { token }),
    createSuite: (data: { name: string; description: string; target_type: string; target_id: string }, token: string) =>
      request<EvalSuite>("/api/evals/suites", { method: "POST", body: JSON.stringify(data), token }),
    deleteSuite: (id: string, token: string) =>
      request<void>(`/api/evals/suites/${id}`, { method: "DELETE", token }),
    createCase: (suiteId: string, data: { name: string; input: Record<string, unknown>; expected_output?: Record<string, unknown>; grading_method: string; grading_config?: Record<string, unknown> }, token: string) =>
      request<EvalCase>(`/api/evals/suites/${suiteId}/cases`, { method: "POST", body: JSON.stringify(data), token }),
    deleteCase: (caseId: string, token: string) =>
      request<void>(`/api/evals/cases/${caseId}`, { method: "DELETE", token }),
    runSuite: (suiteId: string, data: { model?: string } | undefined, token: string) =>
      request<EvalRun>(`/api/evals/suites/${suiteId}/run`, { method: "POST", body: JSON.stringify(data || {}), token }),
    listRuns: (suiteId: string, token: string) =>
      request<EvalRun[]>(`/api/evals/suites/${suiteId}/runs`, { token }),
    getRun: (runId: string, token: string) =>
      request<EvalRun>(`/api/evals/runs/${runId}`, { token }),
    compareRuns: (runId: string, otherRunId: string, token: string) =>
      request<Record<string, unknown>>(`/api/evals/runs/${runId}/compare/${otherRunId}`, { token }),
  },
  approvals: {
    list: (status: string, token: string) =>
      request<Approval[]>(`/api/approvals?status=${status}`, { token }),
    get: (id: string, token: string) => request<Approval>(`/api/approvals/${id}`, { token }),
    approve: (id: string, feedback: string, token: string) =>
      request<Approval>(`/api/approvals/${id}/approve`, { method: "POST", body: JSON.stringify({ feedback }), token }),
    reject: (id: string, feedback: string, token: string) =>
      request<Approval>(`/api/approvals/${id}/reject`, { method: "POST", body: JSON.stringify({ feedback }), token }),
  },
  triggers: {
    list: (token: string) => request<Trigger[]>("/api/triggers", { token }),
    create: (data: { type: string; config: Record<string, unknown>; target_type: string; target_id: string }, token: string) =>
      request<Trigger>("/api/triggers", { method: "POST", body: JSON.stringify(data), token }),
    update: (id: string, data: { config?: Record<string, unknown>; enabled?: boolean }, token: string) =>
      request<Trigger>(`/api/triggers/${id}`, { method: "PUT", body: JSON.stringify(data), token }),
    delete: (id: string, token: string) =>
      request<void>(`/api/triggers/${id}`, { method: "DELETE", token }),
    toggle: (id: string, token: string) =>
      request<Trigger>(`/api/triggers/${id}/toggle`, { method: "PUT", token }),
    history: (id: string, token: string) =>
      request<TriggerHistory[]>(`/api/triggers/${id}/history`, { token }),
  },
};
