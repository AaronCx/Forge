import type { Blueprint, BlueprintNode, NodeTypeInfo } from "@/lib/api";

const NOW = "2026-04-20T10:00:00Z";

function nodeTypeInfo(
  key: string,
  display_name: string,
  category: string,
  node_class: "deterministic" | "agent",
  description = ""
): NodeTypeInfo {
  return {
    key,
    display_name,
    category,
    node_class,
    description,
    input_schema: {},
    output_schema: {},
  };
}

export const DEMO_NODE_TYPES: NodeTypeInfo[] = [
  nodeTypeInfo("fetch_url", "Fetch URL", "context", "deterministic"),
  nodeTypeInfo("knowledge_retrieval", "Knowledge Retrieval", "context", "deterministic"),
  nodeTypeInfo("template_renderer", "Template Renderer", "transform", "deterministic"),
  nodeTypeInfo("output_formatter", "Output Formatter", "output", "deterministic"),
  nodeTypeInfo("json_validator", "JSON Validator", "validate", "deterministic"),
  nodeTypeInfo("approval_gate", "Approval Gate", "validate", "deterministic"),
  nodeTypeInfo("llm_summarize", "Summarize", "agent", "agent"),
  nodeTypeInfo("llm_extract", "Extract", "agent", "agent"),
  nodeTypeInfo("llm_generate", "Generate", "agent", "agent"),
  nodeTypeInfo("llm_review", "Review", "agent", "agent"),
  nodeTypeInfo("agent_spawn", "Spawn Agent", "agent", "agent"),
  nodeTypeInfo("agent_prompt", "Prompt Agent", "agent", "agent"),
  nodeTypeInfo("agent_wait", "Wait for Agent", "agent", "agent"),
  nodeTypeInfo("agent_result", "Read Agent Result", "agent", "agent"),
  nodeTypeInfo("steer_see", "Steer: See", "agent", "agent"),
  nodeTypeInfo("steer_click", "Steer: Click", "agent", "agent"),
  nodeTypeInfo("steer_type", "Steer: Type", "agent", "agent"),
  nodeTypeInfo("cu_planner", "CU Planner", "agent", "agent"),
  nodeTypeInfo("cu_verifier", "CU Verifier", "agent", "agent"),
];

function n(
  id: string,
  type: string,
  label: string,
  x: number,
  y: number,
  dependencies: string[] = [],
  config: Record<string, unknown> = {}
): BlueprintNode {
  return { id, type, label, config, dependencies, position: { x, y } };
}

const blueprint = (
  id: string,
  name: string,
  description: string,
  nodes: BlueprintNode[]
): Blueprint => ({
  id,
  user_id: "demo",
  name,
  description,
  version: 1,
  is_template: false,
  nodes,
  context_config: {},
  tool_scope: [],
  retry_policy: { max_retries: 1 },
  output_schema: null,
  created_at: NOW,
  updated_at: NOW,
});

const research_summarize_output = blueprint(
  "demo-bp-research-summarize",
  "Research → Summarize → Output",
  "Single-agent linear DAG: pulls a URL, summarizes it, and formats the result.",
  [
    n("ctx", "fetch_url", "Fetch Source", 60, 160, [], { url: "https://example.com/article" }),
    n("sum", "llm_summarize", "Summarize", 360, 160, ["ctx"], { model: "gpt-4o-mini" }),
    n("out", "output_formatter", "Output", 660, 160, ["sum"], { format: "markdown" }),
  ]
);

const multi_agent_pipeline = blueprint(
  "demo-bp-multi-agent",
  "Multi-agent research pipeline",
  "Research Agent → Data Extractor → Code Reviewer with a conditional approval branch.",
  [
    n("research", "llm_generate", "Research Agent", 60, 100, [], { model: "gpt-4o-mini" }),
    n("extract", "llm_extract", "Data Extractor", 360, 100, ["research"], { model: "gpt-4o-mini" }),
    n("review", "llm_review", "Code Reviewer", 660, 100, ["extract"], { model: "gpt-4o-mini" }),
    n("gate", "approval_gate", "Reviewer Approval", 660, 280, ["review"], { mode: "manual" }),
    n("out", "output_formatter", "Output", 960, 190, ["gate"], { format: "json" }),
  ]
);

const rag_qa = blueprint(
  "demo-bp-rag-qa",
  "RAG-backed Q&A",
  "Retrieve from a knowledge base, render a prompt template, generate, and format.",
  [
    n("kb", "knowledge_retrieval", "KB Retrieval", 60, 160, [], { collection: "docs", k: 4 }),
    n("tpl", "template_renderer", "Render Prompt", 360, 160, ["kb"], { template: "qa.md" }),
    n("gen", "llm_generate", "Generate Answer", 660, 160, ["tpl"], { model: "gpt-4o-mini" }),
    n("out", "output_formatter", "Output", 960, 160, ["gen"], { format: "markdown" }),
  ]
);

const agent_on_agent = blueprint(
  "demo-bp-agent-on-agent",
  "Agent-on-agent: Claude Code worker",
  "Spawn a Claude Code subagent, prompt it, wait for completion, and read the result.",
  [
    n("spawn", "agent_spawn", "Spawn Claude Code", 60, 160, [], { worker: "claude-code" }),
    n("prompt", "agent_prompt", "Prompt Agent", 360, 160, ["spawn"], {
      prompt: "Refactor scraper.py for clarity",
    }),
    n("wait", "agent_wait", "Wait", 660, 160, ["prompt"], { timeout_s: 120 }),
    n("result", "agent_result", "Read Result", 960, 160, ["wait"]),
  ]
);

const computer_use = blueprint(
  "demo-bp-computer-use",
  "Computer Use demo",
  "GUI automation pipeline that sees the screen, plans, clicks, types, and verifies.",
  [
    n("see", "steer_see", "Capture Screen", 60, 160, [], { target: "screen" }),
    n("plan", "cu_planner", "Plan Next Step", 360, 160, ["see"], { model: "gpt-4o-mini" }),
    n("click", "steer_click", "Click Target", 660, 80, ["plan"], { selector: "button.primary" }),
    n("type", "steer_type", "Type Input", 660, 240, ["plan"], { text: "hello forge" }),
    n("verify", "cu_verifier", "Verify Outcome", 960, 160, ["click", "type"]),
  ]
);

export const DEMO_BLUEPRINTS: Blueprint[] = [
  research_summarize_output,
  multi_agent_pipeline,
  rag_qa,
  agent_on_agent,
  computer_use,
];

export const DEMO_STARTER_BLUEPRINT: Blueprint = blueprint(
  "demo-bp-starter",
  "Untitled blueprint",
  "Drag nodes from the palette and connect them to build your workflow.",
  [
    n("input", "fetch_url", "Input", 100, 200, [], { url: "" }),
    n("agent", "llm_generate", "Agent", 380, 200, ["input"], { model: "gpt-4o-mini" }),
    n("output", "output_formatter", "Output", 660, 200, ["agent"], { format: "markdown" }),
  ]
);

export function findDemoBlueprint(id: string): Blueprint | undefined {
  if (id === DEMO_STARTER_BLUEPRINT.id) return DEMO_STARTER_BLUEPRINT;
  return DEMO_BLUEPRINTS.find((bp) => bp.id === id);
}
