import Link from "next/link";
import { Button } from "@/components/ui/button";
import { LandingHeader } from "@/components/LandingHeader";

const features = [
  {
    title: "Agent Builder",
    desc: "Design multi-step AI workflows with a visual editor. Chain LLM calls, configure tools, and set system prompts.",
  },
  {
    title: "Multi-Agent Orchestration",
    desc: "Submit high-level objectives and let agents decompose, coordinate, and execute tasks with dependency graphs.",
  },
  {
    title: "Live Monitoring",
    desc: "Real-time dashboard with heartbeat tracking, SSE-powered updates, and stalled agent detection.",
  },
  {
    title: "Inter-Agent Messaging",
    desc: "Agents communicate via typed messages — handoffs, requests, responses — for seamless coordination.",
  },
  {
    title: "Cost Analytics",
    desc: "Track token usage per agent, model, and run. Get daily projections and breakdown reports.",
  },
  {
    title: "CLI + API",
    desc: "Full CLI with live TUI dashboard, plus REST API with SSE streaming for programmatic access.",
  },
];

const templates = [
  {
    title: "Document Analyzer",
    desc: "Upload PDFs and get structured summaries, key entities, and action items.",
  },
  {
    title: "Research Agent",
    desc: "Give a topic — the agent searches, synthesizes, and generates a report.",
  },
  {
    title: "Data Extractor",
    desc: "Paste unstructured text and extract structured JSON or CSV data.",
  },
  {
    title: "Code Reviewer",
    desc: "Submit code for automated review — bugs, security issues, and improvements.",
  },
];

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col">
      <LandingHeader />

      <main className="flex flex-1 flex-col items-center px-6">
        {/* Hero */}
        <div className="mx-auto max-w-3xl pt-24 pb-16 text-center">
          <h1 className="text-5xl font-bold tracking-tight sm:text-6xl">
            Build AI Agents That{" "}
            <span className="text-primary">Work For You</span>
          </h1>
          <p className="mt-6 text-lg text-muted-foreground leading-8">
            Create, orchestrate, and monitor multi-agent AI workflows with tool
            use. From single-agent tasks to coordinated multi-agent objectives —
            all through a clean web interface, CLI, or API.
          </p>
          <div className="mt-10 flex items-center justify-center gap-4">
            <Link href="/dashboard">
              <Button size="lg" className="text-base px-8">
                Start Building
              </Button>
            </Link>
            <Link href="/dashboard">
              <Button variant="outline" size="lg" className="text-base px-8">
                Try Demo
              </Button>
            </Link>
          </div>
        </div>

        {/* Features */}
        <div className="mx-auto max-w-5xl w-full pb-16">
          <h2 className="text-2xl font-bold text-center mb-8">
            Everything you need for AI agent workflows
          </h2>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((f) => (
              <div
                key={f.title}
                className="rounded-xl border border-border bg-card p-6"
              >
                <h3 className="font-semibold">{f.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Templates */}
        <div className="mx-auto max-w-5xl w-full pb-16">
          <h2 className="text-2xl font-bold text-center mb-8">
            Pre-built agent templates
          </h2>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {templates.map((t) => (
              <div
                key={t.title}
                className="rounded-xl border border-border bg-card p-6"
              >
                <h3 className="font-semibold">{t.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{t.desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Tech stack */}
        <div className="mx-auto max-w-3xl w-full pb-20 text-center">
          <h2 className="text-2xl font-bold mb-4">Built with modern tools</h2>
          <div className="flex flex-wrap items-center justify-center gap-3">
            {[
              "Next.js 14",
              "FastAPI",
              "LangChain",
              "OpenAI",
              "SQLite / Supabase",
              "TypeScript",
              "Python 3.12",
              "Tailwind CSS",
            ].map((tech) => (
              <span
                key={tech}
                className="rounded-full border border-border px-4 py-1.5 text-sm text-muted-foreground"
              >
                {tech}
              </span>
            ))}
          </div>
        </div>
      </main>

      <footer className="border-t border-border py-8 text-center text-sm text-muted-foreground">
        Forge — Open source AI agent platform
      </footer>
    </div>
  );
}
