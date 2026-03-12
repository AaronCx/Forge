"use client";

import { useState, useRef } from "react";
import { supabase } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import MessageFeed from "@/components/dashboard/MessageFeed";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TOOL_OPTIONS = [
  "web_search",
  "document_reader",
  "code_executor",
  "data_extractor",
  "summarizer",
];

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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!objective.trim() || running) return;

    setRunning(true);
    setPlan([]);
    setEvents([]);
    setResult("");
    setTaskStates({});
    setGroupId("");

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
            } catch {}
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
          Submit a high-level objective and let agents decompose and execute it
        </p>
      </div>

      {/* Input form */}
      <Card>
        <CardContent className="pt-6">
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
                {TOOL_OPTIONS.map((tool) => (
                  <button
                    key={tool}
                    type="button"
                    onClick={() => toggleTool(tool)}
                    className={`rounded-md border px-3 py-1 text-xs transition-colors ${
                      selectedTools.includes(tool)
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border text-muted-foreground hover:border-primary"
                    }`}
                  >
                    {tool.replace("_", " ")}
                  </button>
                ))}
              </div>
            </div>
            <Button type="submit" disabled={running || !objective.trim()}>
              {running ? "Running..." : "Start Orchestration"}
            </Button>
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
