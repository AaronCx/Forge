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
    run: (id: string, input: { input_text: string }, token: string) =>
      `${API_URL}/api/blueprints/${id}/run`,
    getRun: (runId: string, token: string) => request<BlueprintRun>(`/api/blueprints/runs/${runId}`, { token }),
    listRuns: (id: string, token: string) => request<BlueprintRun[]>(`/api/blueprints/${id}/runs`, { token }),
  },
};
