/**
 * Demo/mock data for the dashboard when running in demo mode.
 * Activated via ?demo=true query parameter.
 */

export const DEMO_STATS = {
  total_agents: 8,
  total_runs: 147,
  total_tokens: 482_350,
  runs_this_hour: 4,
};

export const DEMO_AGENTS = [
  {
    id: "demo-1",
    user_id: "demo",
    name: "Research Agent",
    description: "Searches the web and synthesizes findings into reports",
    system_prompt: "You are a research agent.",
    tools: ["web_search", "summarizer"],
    workflow_steps: ["Search for information", "Synthesize findings", "Generate report"],
    is_template: true,
    created_at: "2026-03-10T10:00:00Z",
    updated_at: "2026-03-12T08:00:00Z",
  },
  {
    id: "demo-2",
    user_id: "demo",
    name: "Data Extractor",
    description: "Extracts structured data from unstructured text",
    system_prompt: "You are a data extraction agent.",
    tools: ["data_extractor"],
    workflow_steps: ["Parse input", "Extract entities", "Format output"],
    is_template: true,
    created_at: "2026-03-10T10:00:00Z",
    updated_at: "2026-03-11T14:00:00Z",
  },
  {
    id: "demo-3",
    user_id: "demo",
    name: "Code Reviewer",
    description: "Reviews code for bugs, security issues, and improvements",
    system_prompt: "You are a code review agent.",
    tools: ["code_executor"],
    workflow_steps: ["Analyze code", "Check for issues", "Generate review"],
    is_template: false,
    created_at: "2026-03-11T09:00:00Z",
    updated_at: "2026-03-12T12:00:00Z",
  },
];

export const DEMO_METRICS = {
  active_runs: 2,
  total_agents: 8,
  tokens_today: 24_500,
  cost_today: 0.0312,
};

export const DEMO_ACTIVE_AGENTS = [
  {
    id: "hb-1",
    agent_id: "demo-1",
    run_id: "run-demo-1",
    state: "running",
    current_step: 2,
    total_steps: 3,
    tokens_used: 1250,
    cost_estimate: 0.0015,
    output_preview: "Found 12 relevant sources on AI agent architectures...",
    agents: { name: "Research Agent", description: "Web research", tools: ["web_search"] },
    updated_at: "2026-03-12T12:30:00Z",
  },
  {
    id: "hb-2",
    agent_id: "demo-3",
    run_id: null,
    state: "starting",
    current_step: 0,
    total_steps: 3,
    tokens_used: 0,
    cost_estimate: 0,
    output_preview: "",
    agents: { name: "Code Reviewer", description: "Code review", tools: ["code_executor"] },
    updated_at: "2026-03-12T12:31:00Z",
  },
];

export const DEMO_TIMELINE = [
  {
    id: "ev-1",
    agent_id: "demo-1",
    agent_name: "Research Agent",
    run_id: "run-demo-1",
    state: "running",
    severity: "info",
    current_step: 2,
    total_steps: 3,
    tokens_used: 1250,
    cost_estimate: 0.0015,
    output_preview: "Found 12 relevant sources on AI agent architectures...",
    updated_at: "2026-03-12T12:30:00Z",
  },
  {
    id: "ev-2",
    agent_id: "demo-2",
    agent_name: "Data Extractor",
    run_id: "run-demo-2",
    state: "completed",
    severity: "success",
    current_step: 3,
    total_steps: 3,
    tokens_used: 890,
    cost_estimate: 0.001,
    output_preview: "Extracted 24 entities from input document.",
    updated_at: "2026-03-12T12:25:00Z",
  },
  {
    id: "ev-3",
    agent_id: "demo-3",
    agent_name: "Code Reviewer",
    run_id: null,
    state: "starting",
    severity: "info",
    current_step: 0,
    total_steps: 3,
    tokens_used: 0,
    cost_estimate: 0,
    output_preview: "",
    updated_at: "2026-03-12T12:31:00Z",
  },
];

export const DEMO_COST_SUMMARY = {
  period: "today",
  total_input_tokens: 18_200,
  total_output_tokens: 6_300,
  total_tokens: 24_500,
  total_cost: 0.0312,
  request_count: 47,
};

export const DEMO_COST_PROJECTION = {
  daily_average: 0.028,
  weekly_total: 0.196,
  monthly_projection: 0.84,
  tokens_per_day: 22_000,
};

export function isDemoMode(): boolean {
  if (typeof window === "undefined") return false;
  return (
    new URLSearchParams(window.location.search).has("demo") ||
    document.cookie.includes("agentforge_demo=1")
  );
}
