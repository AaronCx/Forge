"use client";

import { useState, useRef, useEffect } from "react";
import { supabase } from "@/lib/supabase";
import { isDemoMode } from "@/lib/demo-data";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import MessageFeed from "@/components/dashboard/MessageFeed";
import { API_URL, AVAILABLE_TOOLS } from "@/lib/constants";

const roleColors: Record<string, string> = {
  coordinator: "bg-purple-500",
  supervisor: "bg-blue-500",
  worker: "bg-green-500",
  scout: "bg-cyan-500",
  reviewer: "bg-orange-500",
};

interface TaskPlan {
  description: string;
  role: string;
  dependencies: number[];
  tools: string[];
}

interface TaskEvent {
  type: string;
  data: unknown;
  group_id?: string;
}

type SavedWorkflow = {
  id: string;
  name: string;
  description: string;
  workflow_spec: {
    title: string;
    stages: { id: string; kind: string; agents: { role: string }[] }[];
  };
};

type StageProgress = {
  stage_id: string;
  agents_running: number;
  agents_done: number;
  agents_total: number;
  tokens_spent: number;
  elapsed_seconds: number;
};

type LiveRun = {
  workflowId: string;
  title: string;
  status: "running" | "completed" | "failed";
  stages: Record<string, StageProgress>;
  output: string;
  error: string;
};

function DynamicWorkflows() {
  const [workflows, setWorkflows] = useState<SavedWorkflow[]>([]);
  const [run, setRun] = useState<LiveRun | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (isDemoMode()) {
      setLoaded(true);
      return;
    }
    void (async () => {
      try {
        const { data } = await supabase.auth.getSession();
        if (!data.session) return;
        const res = await fetch(`${API_URL}/api/workflows`, {
          headers: { Authorization: `Bearer ${data.session.access_token}` },
        });
        if (res.ok) setWorkflows(await res.json());
      } catch {
        // saved workflows are optional; the page still renders
      } finally {
        setLoaded(true);
      }
    })();
  }, []);

  async function runWorkflow(wf: SavedWorkflow) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;
    setRun({ workflowId: wf.id, title: wf.name, status: "running", stages: {}, output: "", error: "" });
    try {
      const res = await fetch(`${API_URL}/api/workflows/${wf.id}/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${data.session.access_token}`,
        },
        body: JSON.stringify({ confirm: true }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        setRun((prev) => prev && { ...prev, status: "failed", error: String(err.detail || res.status) });
        return;
      }
      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (reader) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") continue;
          try {
            const event = JSON.parse(payload);
            const d = event.data as Record<string, unknown>;
            setRun((prev) => {
              if (!prev) return prev;
              if (event.type === "workflow_progress") {
                const p = d as unknown as StageProgress;
                return { ...prev, stages: { ...prev.stages, [p.stage_id]: p } };
              }
              if (event.type === "workflow_error") return { ...prev, error: String(d?.error ?? "") };
              if (event.type === "workflow_done") {
                return {
                  ...prev,
                  status: (d?.status as LiveRun["status"]) || "completed",
                  output: String(d?.output ?? ""),
                  error: String(d?.error ?? ""),
                };
              }
              return prev;
            });
          } catch {
            // skip malformed SSE events
          }
        }
      }
    } catch (err: unknown) {
      setRun((prev) => prev && { ...prev, status: "failed", error: String(err) });
    }
  }

  if (!loaded) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">Dynamic workflows</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {workflows.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-seeded="true">
            No saved workflows yet. Ask for one in Chat (effort: ultra, or say
            “workflow”), then Save the proposed plan — it lands here as a
            rerunnable blueprint.
          </p>
        ) : (
          <div className="space-y-2">
            {workflows.map((wf) => {
              const stages = wf.workflow_spec?.stages ?? [];
              const agents = stages.reduce((n, s) => n + (s.agents?.length ?? 0), 0);
              return (
                <div key={wf.id} className="flex items-center justify-between rounded-lg border border-border p-3">
                  <div>
                    <div className="text-sm font-medium">{wf.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {stages.length} stage{stages.length === 1 ? "" : "s"} · {agents} agent
                      {agents === 1 ? "" : "s"}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    onClick={() => void runWorkflow(wf)}
                    disabled={run?.status === "running"}
                  >
                    Run
                  </Button>
                </div>
              );
            })}
          </div>
        )}

        {run && (
          <div className="rounded-lg border border-border p-3">
            <div className="flex items-center gap-2">
              <Badge variant={run.status === "failed" ? "destructive" : "default"}>
                {run.status}
              </Badge>
              <span className="text-sm font-medium">{run.title}</span>
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
              <div className="mt-2 max-h-60 overflow-y-auto whitespace-pre-wrap rounded-md bg-muted p-2 text-sm">
                {run.output}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function OrchestratePage() {
  const [objective, setObjective] = useState("");
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [plan, setPlan] = useState<TaskPlan[]>([]);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [result, setResult] = useState("");
  const [taskStates, setTaskStates] = useState<Record<number, string>>({});
  const [groupId, setGroupId] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!objective.trim() || running) return;

    setRunning(true);
    setPlan([]);
    setEvents([]);
    setResult("");
    setTaskStates({});
    setGroupId("");

    if (isDemoMode()) {
      setEvents([{ type: "error", data: "Orchestration is disabled in demo mode. Sign up to use this feature." }]);
      setRunning(false);
      return;
    }

    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${API_URL}/api/orchestrate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${data.session.access_token}`,
        },
        body: JSON.stringify({ objective, tools: selectedTools }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        setEvents((prev) => [...prev, { type: "error", data: err.detail || `HTTP ${res.status}` }]);
        setRunning(false);
        return;
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (reader) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6));
              setEvents((prev) => [...prev, event]);

              if (event.type === "plan") {
                setPlan(event.data);
              } else if (event.type === "task_start") {
                setTaskStates((prev) => ({ ...prev, [event.data.index]: "running" }));
              } else if (event.type === "task_done") {
                setTaskStates((prev) => ({ ...prev, [event.data.index]: "completed" }));
              } else if (event.type === "result") {
                setResult(event.data);
                if (event.group_id) setGroupId(event.group_id);
              }
            } catch {
              // Skip malformed SSE events
            }
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== "AbortError") {
        setEvents((prev) => [...prev, { type: "error", data: String(err) }]);
      }
    } finally {
      setRunning(false);
    }
  }

  function toggleTool(tool: string) {
    setSelectedTools((prev) =>
      prev.includes(tool) ? prev.filter((t) => t !== tool) : [...prev, tool]
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Orchestrate</h1>
        <p className="mt-1 text-muted-foreground">
          Live view of dynamic workflow runs — plans proposed in Chat, saved to
          the library, and re-run from here
        </p>
      </div>

      {/* Dynamic workflows (Phase 9) — the primary surface */}
      <DynamicWorkflows />

      {/* Legacy coordinator/supervisor/worker orchestrator (deprecated —
          superseded by dynamic workflows; kept during the deprecation window) */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">
            Legacy orchestrator{" "}
            <Badge variant="outline" className="ml-1 align-middle text-[10px]">
              deprecated
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-2">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium">Objective</label>
              <textarea
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                placeholder="Describe what you want to accomplish..."
                className="mt-1 w-full rounded-md border border-border bg-background p-3 text-sm"
                rows={3}
              />
            </div>
            <div>
              <label className="text-sm font-medium">Tools</label>
              <div className="mt-1 flex flex-wrap gap-2">
                {AVAILABLE_TOOLS.map((tool) => (
                  <button
                    key={tool.id}
                    type="button"
                    onClick={() => toggleTool(tool.id)}
                    className={`rounded-md border px-3 py-1 text-xs transition-colors ${
                      selectedTools.includes(tool.id)
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border text-muted-foreground hover:border-primary"
                    }`}
                  >
                    {tool.name}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={running || !objective.trim()}>
                {running ? "Running..." : "Start Orchestration"}
              </Button>
              {running && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    abortRef.current?.abort();
                    setRunning(false);
                  }}
                >
                  Cancel
                </Button>
              )}
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Task Plan */}
      {plan.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Task Plan</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {plan.map((task, i) => {
                const state = taskStates[i] || "pending";
                return (
                  <div
                    key={i}
                    className="flex items-start gap-3 rounded-lg border border-border p-3"
                  >
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold">
                      {i + 1}
                    </span>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <Badge
                          className={`text-[10px] text-white ${roleColors[task.role] || "bg-gray-500"}`}
                        >
                          {task.role}
                        </Badge>
                        <Badge
                          variant={
                            state === "completed"
                              ? "default"
                              : state === "running"
                                ? "secondary"
                                : "outline"
                          }
                          className="text-[10px]"
                        >
                          {state}
                        </Badge>
                        {task.dependencies.length > 0 && (
                          <span className="text-[10px] text-muted-foreground">
                            depends on: {task.dependencies.map((d) => d + 1).join(", ")}
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-sm">{task.description}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Event log */}
      {events.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Progress</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-60 space-y-1 overflow-y-auto">
              {events.map((ev, i) => (
                <div key={i} className="flex gap-2 text-xs">
                  <Badge
                    variant={ev.type === "error" ? "destructive" : "outline"}
                    className="shrink-0 text-[10px]"
                  >
                    {ev.type}
                  </Badge>
                  <span className="text-muted-foreground">
                    {typeof ev.data === "string"
                      ? ev.data
                      : (() => {
                          const d = ev.data as Record<string, unknown>;
                          return String(d?.description ?? d?.preview ?? JSON.stringify(ev.data));
                        })()}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Final result */}
      {result && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Result</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="whitespace-pre-wrap rounded-lg bg-muted p-4 text-sm">
              {result}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Agent Messages */}
      {groupId && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">Agent Messages</CardTitle>
          </CardHeader>
          <CardContent>
            <MessageFeed
              groupId={groupId}
              taskNames={plan.map((t, i) => `Task ${i + 1}: ${t.role}`)}
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
