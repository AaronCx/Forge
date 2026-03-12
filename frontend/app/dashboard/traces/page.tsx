"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { api, Trace, TraceStats } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { isDemoMode } from "@/lib/demo-data";

const SPAN_COLORS: Record<string, string> = {
  llm_call: "bg-purple-500",
  tool_call: "bg-blue-500",
  node_execution: "bg-cyan-500",
  agent_step: "bg-green-500",
  blueprint_step: "bg-orange-500",
};

const STATUS_COLORS: Record<string, string> = {
  ok: "bg-green-500",
  running: "bg-yellow-500",
  error: "bg-red-500",
  timeout: "bg-orange-500",
};

export default function TracesPage() {
  const [traces, setTraces] = useState<Trace[]>([]);
  const [stats, setStats] = useState<TraceStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTrace, setSelectedTrace] = useState<Trace | null>(null);
  const [filterType, setFilterType] = useState<string>("");

  useEffect(() => {
    if (isDemoMode()) {
      setTraces([]);
      setStats({ total_spans: 0, error_count: 0, error_rate: 0, total_tokens: 0, avg_latency_ms: 0, by_type: {} });
      setLoading(false);
      return;
    }
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterType]);

  async function loadData() {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      const params: { span_type?: string; limit?: number } = { limit: 100 };
      if (filterType) params.span_type = filterType;
      const [traceList, traceStats] = await Promise.all([
        api.traces.list(data.session.access_token, params),
        api.traces.stats(data.session.access_token),
      ]);
      setTraces(traceList);
      setStats(traceStats);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  async function loadTraceTree(traceId: string) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;
    try {
      const tree = await api.traces.tree(traceId, data.session.access_token);
      setSelectedTrace(tree);
    } catch {
      // ignore
    }
  }

  const spanTypes = ["agent_step", "llm_call", "tool_call", "node_execution", "blueprint_step"];

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Traces</h1>
          <p className="mt-1 text-muted-foreground">
            Observe execution spans across agents, blueprints, and LLM calls
          </p>
        </div>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-5">
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground">Total Spans</p>
              <p className="text-2xl font-bold">{stats.total_spans}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground">Errors</p>
              <p className="text-2xl font-bold text-red-500">{stats.error_count}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground">Error Rate</p>
              <p className="text-2xl font-bold">{(stats.error_rate * 100).toFixed(1)}%</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground">Total Tokens</p>
              <p className="text-2xl font-bold">{stats.total_tokens.toLocaleString()}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-muted-foreground">Avg Latency</p>
              <p className="text-2xl font-bold">{stats.avg_latency_ms.toFixed(0)}ms</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <div className="mt-4 flex gap-2">
        <Button
          variant={filterType === "" ? "default" : "outline"}
          size="sm"
          onClick={() => setFilterType("")}
        >
          All
        </Button>
        {spanTypes.map((type) => (
          <Button
            key={type}
            variant={filterType === type ? "default" : "outline"}
            size="sm"
            onClick={() => setFilterType(type)}
          >
            {type.replace("_", " ")}
          </Button>
        ))}
      </div>

      {/* Trace list */}
      <div className="mt-6 space-y-2">
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 animate-pulse rounded-lg bg-muted" />
            ))}
          </div>
        ) : traces.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No traces recorded yet. Traces are automatically created when agents and blueprints run.
          </p>
        ) : (
          traces.map((trace) => (
            <Card
              key={trace.id}
              className="cursor-pointer hover:border-primary/50 transition-colors"
              onClick={() => loadTraceTree(trace.id)}
            >
              <CardContent className="flex items-center gap-3 py-3">
                <div
                  className={`h-2.5 w-2.5 rounded-full ${STATUS_COLORS[trace.status] || "bg-gray-500"}`}
                />
                <Badge variant="outline" className="text-xs">
                  {trace.span_type.replace("_", " ")}
                </Badge>
                <span className="flex-1 truncate text-sm font-medium">
                  {trace.span_name || "Unnamed span"}
                </span>
                {trace.model && (
                  <span className="text-xs text-muted-foreground font-mono">
                    {trace.model}
                  </span>
                )}
                <span className="text-xs text-muted-foreground">
                  {trace.input_tokens + trace.output_tokens > 0
                    ? `${(trace.input_tokens + trace.output_tokens).toLocaleString()} tok`
                    : ""}
                </span>
                <span className="text-xs text-muted-foreground">
                  {trace.latency_ms > 0 ? `${(trace.latency_ms / 1000).toFixed(1)}s` : ""}
                </span>
                <span className="text-xs text-muted-foreground">
                  {new Date(trace.created_at).toLocaleTimeString()}
                </span>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Detail panel */}
      {selectedTrace && (
        <div className="fixed inset-y-0 right-0 w-[480px] border-l border-border bg-card shadow-lg overflow-auto p-6 z-50">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold">Trace Detail</h2>
            <Button variant="ghost" size="sm" onClick={() => setSelectedTrace(null)}>
              Close
            </Button>
          </div>

          <div className="space-y-3 text-sm">
            <div>
              <span className="text-muted-foreground">Type:</span>{" "}
              <Badge variant="outline">{selectedTrace.span_type}</Badge>
            </div>
            <div>
              <span className="text-muted-foreground">Name:</span> {selectedTrace.span_name}
            </div>
            <div>
              <span className="text-muted-foreground">Status:</span>{" "}
              <Badge variant={selectedTrace.status === "error" ? "destructive" : "outline"}>
                {selectedTrace.status}
              </Badge>
            </div>
            {selectedTrace.model && (
              <div>
                <span className="text-muted-foreground">Model:</span>{" "}
                <span className="font-mono">{selectedTrace.model}</span>
                {selectedTrace.provider && (
                  <span className="text-muted-foreground"> ({selectedTrace.provider})</span>
                )}
              </div>
            )}
            <div className="grid grid-cols-3 gap-2">
              <div>
                <p className="text-muted-foreground">Input Tokens</p>
                <p className="font-mono">{selectedTrace.input_tokens.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Output Tokens</p>
                <p className="font-mono">{selectedTrace.output_tokens.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Latency</p>
                <p className="font-mono">{(selectedTrace.latency_ms / 1000).toFixed(2)}s</p>
              </div>
            </div>

            {selectedTrace.input_preview && (
              <div>
                <p className="text-muted-foreground mb-1">Input Preview</p>
                <pre className="rounded bg-muted p-2 text-xs overflow-auto max-h-32">
                  {selectedTrace.input_preview}
                </pre>
              </div>
            )}

            {selectedTrace.output_preview && (
              <div>
                <p className="text-muted-foreground mb-1">Output Preview</p>
                <pre className="rounded bg-muted p-2 text-xs overflow-auto max-h-32">
                  {selectedTrace.output_preview}
                </pre>
              </div>
            )}

            {selectedTrace.error_message && (
              <div>
                <p className="text-red-500 mb-1">Error</p>
                <pre className="rounded bg-red-950/20 p-2 text-xs text-red-400 overflow-auto max-h-24">
                  {selectedTrace.error_message}
                </pre>
              </div>
            )}

            {/* Child spans */}
            {selectedTrace.children && selectedTrace.children.length > 0 && (
              <div>
                <p className="text-muted-foreground mb-2 font-medium">
                  Child Spans ({selectedTrace.children.length})
                </p>
                <div className="space-y-1">
                  {selectedTrace.children.map((child) => (
                    <div
                      key={child.id}
                      className="flex items-center gap-2 rounded bg-muted/50 p-2 text-xs"
                    >
                      <div
                        className={`h-2 w-2 rounded-full ${SPAN_COLORS[child.span_type] || "bg-gray-500"}`}
                      />
                      <span className="truncate flex-1">{child.span_name}</span>
                      <span className="text-muted-foreground">
                        {child.latency_ms > 0 ? `${(child.latency_ms / 1000).toFixed(1)}s` : ""}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="text-xs text-muted-foreground pt-2 border-t">
              <p>ID: {selectedTrace.id}</p>
              {selectedTrace.run_id && <p>Run: {selectedTrace.run_id}</p>}
              {selectedTrace.agent_id && <p>Agent: {selectedTrace.agent_id}</p>}
              <p>Started: {new Date(selectedTrace.started_at).toLocaleString()}</p>
              {selectedTrace.ended_at && (
                <p>Ended: {new Date(selectedTrace.ended_at).toLocaleString()}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
