import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

// Mock next/link since we're not in a Next.js context
vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

describe("StatsCards", () => {
  it("renders all stat values", async () => {
    const { StatsCards } = await import("@/components/dashboard/StatsCards");
    const stats = {
      total_agents: 5,
      total_runs: 42,
      total_tokens: 12345,
      runs_this_hour: 3,
    };

    render(<StatsCards stats={stats} loading={false} />);

    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("12,345")).toBeInTheDocument();
    expect(screen.getByText("3/10")).toBeInTheDocument();
  });

  it("shows loading state", async () => {
    const { StatsCards } = await import("@/components/dashboard/StatsCards");
    const stats = {
      total_agents: 0,
      total_runs: 0,
      total_tokens: 0,
      runs_this_hour: 0,
    };

    const { container } = render(<StatsCards stats={stats} loading={true} />);

    const skeletons = container.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBe(4);
  });

  it("renders all card titles", async () => {
    const { StatsCards } = await import("@/components/dashboard/StatsCards");
    const stats = {
      total_agents: 0,
      total_runs: 0,
      total_tokens: 0,
      runs_this_hour: 0,
    };

    render(<StatsCards stats={stats} loading={false} />);

    expect(screen.getByText("Total Agents")).toBeInTheDocument();
    expect(screen.getByText("Total Runs")).toBeInTheDocument();
    expect(screen.getByText("Tokens Used")).toBeInTheDocument();
    expect(screen.getByText("Runs This Hour")).toBeInTheDocument();
  });
});

describe("StepLog", () => {
  it("renders empty state message", async () => {
    const { StepLog } = await import("@/components/runner/StepLog");

    render(<StepLog logs={[]} />);

    expect(
      screen.getByText("Step execution log will appear here...")
    ).toBeInTheDocument();
  });

  it("renders step entries with string data", async () => {
    const { StepLog } = await import("@/components/runner/StepLog");

    const logs = [
      { type: "step", data: "Analyzing input..." },
      { type: "done", data: "Complete" },
    ];

    render(<StepLog logs={logs} />);

    expect(screen.getByText("Analyzing input...")).toBeInTheDocument();
    expect(screen.getByText("Complete")).toBeInTheDocument();
  });

  it("renders step entries with object data and duration", async () => {
    const { StepLog } = await import("@/components/runner/StepLog");

    const logs = [
      { type: "step", data: { step: 1, result: "Extracted entities", duration_ms: 150 } },
    ];

    render(<StepLog logs={logs} />);

    expect(screen.getByText("Extracted entities")).toBeInTheDocument();
    expect(screen.getByText("150ms")).toBeInTheDocument();
  });
});

describe("ToolSelector", () => {
  it("renders all available tools", async () => {
    const { ToolSelector } = await import("@/components/agents/ToolSelector");

    render(<ToolSelector selected={[]} onChange={() => {}} />);

    expect(screen.getByText("Web Search")).toBeInTheDocument();
    expect(screen.getByText("Document Reader")).toBeInTheDocument();
    expect(screen.getByText("Code Executor")).toBeInTheDocument();
    expect(screen.getByText("Data Extractor")).toBeInTheDocument();
    expect(screen.getByText("Summarizer")).toBeInTheDocument();
  });

  it("shows Active badge for selected tools", async () => {
    const { ToolSelector } = await import("@/components/agents/ToolSelector");

    render(<ToolSelector selected={["web_search"]} onChange={() => {}} />);

    const badges = screen.getAllByText("Active");
    expect(badges.length).toBe(1);
  });

  it("calls onChange when toggling a tool", async () => {
    const { ToolSelector } = await import("@/components/agents/ToolSelector");
    const onChange = vi.fn();

    render(<ToolSelector selected={[]} onChange={onChange} />);

    fireEvent.click(screen.getByText("Web Search"));
    expect(onChange).toHaveBeenCalledWith(["web_search"]);
  });
});

describe("WorkflowEditor", () => {
  it("renders empty state message", async () => {
    const { WorkflowEditor } = await import("@/components/agents/WorkflowEditor");

    render(<WorkflowEditor steps={[]} onChange={() => {}} />);

    expect(
      screen.getByText(/No workflow steps defined/)
    ).toBeInTheDocument();
  });

  it("renders existing steps with inputs", async () => {
    const { WorkflowEditor } = await import("@/components/agents/WorkflowEditor");

    render(
      <WorkflowEditor
        steps={["Extract data", "Summarize results"]}
        onChange={() => {}}
      />
    );

    const inputs = screen.getAllByRole("textbox");
    expect(inputs.length).toBe(2);
    expect(inputs[0]).toHaveValue("Extract data");
    expect(inputs[1]).toHaveValue("Summarize results");
  });

  it("calls onChange when adding a step", async () => {
    const { WorkflowEditor } = await import("@/components/agents/WorkflowEditor");
    const onChange = vi.fn();

    render(<WorkflowEditor steps={["Step 1"]} onChange={onChange} />);

    fireEvent.click(screen.getByText("Add Step"));
    expect(onChange).toHaveBeenCalledWith(["Step 1", ""]);
  });
});

describe("AgentCard", () => {
  it("renders agent name and description", async () => {
    const { AgentCard } = await import("@/components/agents/AgentCard");

    const agent = {
      id: "1",
      user_id: "u1",
      name: "Research Bot",
      description: "Searches the web for information",
      system_prompt: "You are a research agent",
      tools: ["web_search"],
      workflow_steps: [],
      model: null,
      is_template: false,
      created_at: "2026-03-10T00:00:00Z",
      updated_at: "2026-03-10T00:00:00Z",
    };

    render(<AgentCard agent={agent} />);

    expect(screen.getByText("Research Bot")).toBeInTheDocument();
    expect(
      screen.getByText("Searches the web for information")
    ).toBeInTheDocument();
  });

  it("shows Template badge for template agents", async () => {
    const { AgentCard } = await import("@/components/agents/AgentCard");

    const agent = {
      id: "1",
      user_id: "u1",
      name: "Template Agent",
      description: "A template",
      system_prompt: "You are a template",
      tools: [],
      workflow_steps: [],
      model: null,
      is_template: true,
      created_at: "2026-03-10T00:00:00Z",
      updated_at: "2026-03-10T00:00:00Z",
    };

    render(<AgentCard agent={agent} />);

    expect(screen.getByText("Template")).toBeInTheDocument();
  });

  it("renders tool badges", async () => {
    const { AgentCard } = await import("@/components/agents/AgentCard");

    const agent = {
      id: "1",
      user_id: "u1",
      name: "Multi-Tool Agent",
      description: "",
      system_prompt: "test",
      tools: ["web_search", "summarizer"],
      workflow_steps: [],
      model: null,
      is_template: false,
      created_at: "2026-03-10T00:00:00Z",
      updated_at: "2026-03-10T00:00:00Z",
    };

    render(<AgentCard agent={agent} />);

    expect(screen.getByText("web search")).toBeInTheDocument();
    expect(screen.getByText("summarizer")).toBeInTheDocument();
  });
});
