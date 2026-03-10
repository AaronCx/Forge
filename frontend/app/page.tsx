import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm">
              AF
            </div>
            <span className="text-xl font-bold">AgentForge</span>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/login">
              <Button variant="ghost">Log in</Button>
            </Link>
            <Link href="/signup">
              <Button>Get Started</Button>
            </Link>
          </div>
        </div>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-6">
        <div className="mx-auto max-w-3xl text-center">
          <h1 className="text-5xl font-bold tracking-tight sm:text-6xl">
            Build AI Agents That{" "}
            <span className="text-primary">Work For You</span>
          </h1>
          <p className="mt-6 text-lg text-muted-foreground leading-8">
            Create, configure, and run multi-step AI workflow agents with tool
            use. Chain LLM calls, search the web, parse documents, extract data,
            and automate repetitive tasks — all through a clean visual interface.
          </p>
          <div className="mt-10 flex items-center justify-center gap-4">
            <Link href="/signup">
              <Button size="lg" className="text-base px-8">
                Start Building
              </Button>
            </Link>
            <Link href="/login">
              <Button variant="outline" size="lg" className="text-base px-8">
                View Demo
              </Button>
            </Link>
          </div>
        </div>

        <div className="mt-20 grid max-w-5xl grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {[
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
          ].map((template) => (
            <div
              key={template.title}
              className="rounded-xl border border-border bg-card p-6"
            >
              <h3 className="font-semibold">{template.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                {template.desc}
              </p>
            </div>
          ))}
        </div>
      </main>

      <footer className="border-t border-border py-8 text-center text-sm text-muted-foreground">
        Built with Next.js, FastAPI, LangChain & Supabase
      </footer>
    </div>
  );
}
