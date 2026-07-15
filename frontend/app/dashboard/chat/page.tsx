"use client";

import { useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";
import { API_URL } from "@/lib/constants";
import { isDemoMode } from "@/lib/demo-data";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

type ModelCard = { id: string; provider: string; display_name: string; vision: boolean; tools: boolean };
type Turn = { role: "user" | "assistant"; text: string; tools: string[] };

type PlanAgent = { role: string; prompt: string };
type PlanStage = { id: string; kind: string; agents: PlanAgent[]; depends_on: string[] };
type PlanSpec = { title: string; rationale: string; stages: PlanStage[]; worker_model?: string | null };
type Plan = { seq: number; spec: PlanSpec; estimated_tokens: number };

type StageProgress = {
  stage_id: string;
  agents_running: number;
  agents_done: number;
  agents_total: number;
  tokens_spent: number;
  elapsed_seconds: number;
};

type WorkflowRun = {
  title: string;
  status: "running" | "completed" | "failed";
  stages: Record<string, StageProgress>;
  output: string;
  error: string;
};

const EFFORTS = ["standard", "high", "ultra"] as const;

export default function ChatPage() {
  const [demo, setDemo] = useState(false);
  const [models, setModels] = useState<ModelCard[]>([]);
  const [model, setModel] = useState("");
  const [effort, setEffort] = useState<(typeof EFFORTS)[number]>("standard");
  const [sessionId, setSessionId] = useState<string>("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isDemoMode()) {
      setDemo(true);
      return;
    }
    void loadModels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, plan, run]);

  async function token(): Promise<string | null> {
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token ?? null;
  }

  async function loadModels() {
    const t = await token();
    if (!t) return;
    try {
      const res = await fetch(`${API_URL}/api/providers/model-cards`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      if (!res.ok) return;
      const cards: ModelCard[] = await res.json();
      setModels(cards);
      if (cards[0]) setModel(cards[0].id);
    } catch {
      // ignore — chat still works with the server default model
    }
  }

  async function ensureSession(t: string): Promise<string> {
    if (sessionId) return sessionId;
    const res = await fetch(`${API_URL}/api/sessions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json" },
      body: JSON.stringify({ title: "Chat", model, effort }),
    });
    const session = await res.json();
    setSessionId(session.id);
    return session.id;
  }

  async function streamSse(res: Response, onEvent: (event: { type: string; data?: unknown }) => void) {
    const reader = res.body?.getReader();
    if (!reader) return;
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const data = line.slice(6).trim();
        if (data === "[DONE]") continue;
        try {
          onEvent(JSON.parse(data));
        } catch {
          // skip malformed frame
        }
      }
    }
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    const t = await token();
    if (!t) return;
    setInput("");
    setBusy(true);
    setPlan(null);
    setTurns((prev) => [...prev, { role: "user", text, tools: [] }, { role: "assistant", text: "", tools: [] }]);

    try {
      const id = await ensureSession(t);
      const res = await fetch(`${API_URL}/api/sessions/${id}/messages`, {
        method: "POST",
        headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json" },
        body: JSON.stringify({ text, model }),
      });
      await streamSse(res, (event) => {
        if (event.type === "workflow_plan") {
          setPlan(event.data as Plan);
          setTurns((prev) => {
            const next = [...prev];
            next[next.length - 1].text = "Proposed a workflow plan — review it below.";
            return next;
          });
          return;
        }
        setTurns((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          const data = event.data as Record<string, unknown> | string | undefined;
          if (event.type === "token") last.text += String(event.data ?? "");
          else if (event.type === "tool_use") last.tools.push(`→ ${(data as Record<string, unknown>)?.name}`);
          else if (event.type === "tool_result") {
            const d = data as Record<string, unknown>;
            const mark = d?.is_error ? "✗" : "✓";
            last.tools.push(`${mark} ${d?.tool}`);
          }
          return next;
        });
      });
    } catch {
      setTurns((prev) => {
        const next = [...prev];
        next[next.length - 1].text = "Error: could not reach the server.";
        return next;
      });
    } finally {
      setBusy(false);
    }
  }

  async function runPlan(current: Plan) {
    const t = await token();
    if (!t || !sessionId) return;
    setPlan(null);
    setBusy(true);
    setRun({ title: current.spec.title, status: "running", stages: {}, output: "", error: "" });
    try {
      const res = await fetch(`${API_URL}/api/sessions/${sessionId}/workflow/run`, {
        method: "POST",
        headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json" },
        body: JSON.stringify({ plan_seq: current.seq, confirm: true }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        setRun((prev) => prev && { ...prev, status: "failed", error: String(err.detail || res.status) });
        return;
      }
      await streamSse(res, (event) => {
        const d = event.data as Record<string, unknown>;
        setRun((prev) => {
          if (!prev) return prev;
          if (event.type === "workflow_progress") {
            const p = d as unknown as StageProgress;
            return { ...prev, stages: { ...prev.stages, [p.stage_id]: p } };
          }
          if (event.type === "workflow_error") {
            return { ...prev, error: String(d?.error ?? "") };
          }
          if (event.type === "workflow_done") {
            return {
              ...prev,
              status: (d?.status as WorkflowRun["status"]) || "completed",
              output: String(d?.output ?? ""),
              error: String(d?.error ?? ""),
            };
          }
          return prev;
        });
      });
    } catch {
      setRun((prev) => prev && { ...prev, status: "failed", error: "Could not reach the server." });
    } finally {
      setBusy(false);
    }
  }

  async function savePlan(current: Plan) {
    const t = await token();
    if (!t || !sessionId) return;
    try {
      const res = await fetch(`${API_URL}/api/sessions/${sessionId}/workflow/save`, {
        method: "POST",
        headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json" },
        body: JSON.stringify({ plan_seq: current.seq }),
      });
      if (res.ok) {
        const saved = await res.json();
        setPlan(null);
        setTurns((prev) => [
          ...prev,
          { role: "assistant", text: `Workflow saved to the library as “${saved.name}”.`, tools: [] },
        ]);
      }
    } catch {
      // keep the card so the user can retry
    }
  }

  if (demo) {
    return (
      <div>
        <h1 className="text-3xl font-bold">Chat</h1>
        <p className="mt-2 text-muted-foreground">
          Talk to any model with all your tools available. Chat is disabled in demo
          mode — connect a live backend to start a session.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Chat</h1>
        <div className="flex items-center gap-2">
          <select
            className="rounded-md border bg-background px-2 py-1 text-sm"
            value={effort}
            onChange={(e) => setEffort(e.target.value as (typeof EFFORTS)[number])}
            disabled={!!sessionId}
            title="Planner effort — ultra auto-plans multi-agent workflows"
          >
            {EFFORTS.map((ef) => (
              <option key={ef} value={ef}>
                effort: {ef}
              </option>
            ))}
          </select>
          <select
            className="rounded-md border bg-background px-2 py-1 text-sm"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            {models.length === 0 && <option value="">default</option>}
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.display_name} ({m.provider})
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-4 flex-1 space-y-3 overflow-y-auto">
        {turns.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Start a conversation. Your message runs against the selected model with
            the full tool plane available; approvals appear in the Approvals inbox.
            At ultra effort (or with “workflow” in your message) Forge proposes a
            multi-agent plan you can run, edit, or save.
          </p>
        )}
        {turns.map((turn, i) => (
          <Card key={i} className={turn.role === "user" ? "bg-muted" : ""}>
            <CardContent className="py-3">
              <div className="text-xs font-semibold uppercase text-muted-foreground">
                {turn.role}
              </div>
              {turn.tools.map((tool, j) => (
                <div key={j} className="mt-1 text-xs text-muted-foreground">{tool}</div>
              ))}
              <div className="mt-1 whitespace-pre-wrap text-sm">{turn.text}</div>
            </CardContent>
          </Card>
        ))}

        {plan && (
          <Card className="border-primary/50">
            <CardContent className="py-4">
              <div className="flex items-center gap-2">
                <Badge>workflow plan</Badge>
                <span className="font-semibold">{plan.spec.title}</span>
              </div>
              {plan.spec.rationale && (
                <p className="mt-1 text-sm text-muted-foreground">{plan.spec.rationale}</p>
              )}
              <div className="mt-3 space-y-2">
                {plan.spec.stages.map((stage) => (
                  <div key={stage.id} className="rounded-md border p-2 text-sm">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-[10px]">{stage.kind}</Badge>
                      <span className="font-medium">{stage.id}</span>
                      <span className="text-xs text-muted-foreground">
                        {stage.agents.length} agent{stage.agents.length === 1 ? "" : "s"}
                        {stage.depends_on?.length ? ` · after ${stage.depends_on.join(", ")}` : ""}
                      </span>
                    </div>
                    {stage.agents.map((agent, j) => (
                      <div key={j} className="mt-1 text-xs text-muted-foreground">
                        · {agent.role}: {agent.prompt.slice(0, 100)}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                worker model: {plan.spec.worker_model || "session default"} · ~
                {plan.estimated_tokens.toLocaleString()} tokens estimated
              </div>
              <div className="mt-3 flex gap-2">
                <Button size="sm" onClick={() => void runPlan(plan)} disabled={busy}>
                  Run
                </Button>
                <Button size="sm" variant="outline" onClick={() => void savePlan(plan)}>
                  Save
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setPlan(null)}>
                  No
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {run && (
          <Card>
            <CardContent className="py-4">
              <div className="flex items-center gap-2">
                <Badge variant={run.status === "failed" ? "destructive" : "default"}>
                  {run.status === "running" ? "workflow running" : `workflow ${run.status}`}
                </Badge>
                <span className="font-semibold">{run.title}</span>
              </div>
              <div className="mt-2 space-y-1">
                {Object.values(run.stages).map((stage) => (
                  <div key={stage.stage_id} className="text-xs text-muted-foreground">
                    {stage.stage_id}: {stage.agents_done}/{stage.agents_total} done
                    {stage.agents_running > 0 ? `, ${stage.agents_running} running` : ""} ·{" "}
                    {stage.tokens_spent.toLocaleString()} tok · {stage.elapsed_seconds}s
                  </div>
                ))}
              </div>
              {run.error && <div className="mt-2 text-xs text-destructive">{run.error}</div>}
              {run.output && (
                <div className="mt-2 whitespace-pre-wrap rounded-md bg-muted p-2 text-sm">
                  {run.output}
                </div>
              )}
            </CardContent>
          </Card>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="mt-4 flex gap-2">
        <Input
          placeholder="Message…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          disabled={busy}
        />
        <Button onClick={() => void send()} disabled={busy}>
          {busy ? "…" : "Send"}
        </Button>
      </div>
    </div>
  );
}
