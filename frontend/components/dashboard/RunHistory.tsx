"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { api, Run } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { isDemoMode, DEMO_RUNS } from "@/lib/demo-data";

export function RunHistory({ limit }: { limit?: number } = {}) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isDemoMode()) {
      setRuns(limit ? DEMO_RUNS.slice(0, limit) : DEMO_RUNS);
      setLoading(false);
      return;
    }
    async function loadRuns() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) return;

      try {
        const r = await api.runs.list(data.session.access_token);
        setRuns(limit ? r.slice(0, limit) : r);
      } catch {
        // API may not be running
      } finally {
        setLoading(false);
      }
    }
    loadRuns();
  }, [limit]);

  if (loading) {
    return <p className="mt-4 text-sm text-muted-foreground">Loading runs...</p>;
  }

  if (runs.length === 0) {
    return (
      <p className="mt-4 text-sm text-muted-foreground">
        No runs yet. Create an agent and run it to see results here.
      </p>
    );
  }

  return (
    <div className="mt-4 space-y-3">
      {runs.map((run) => (
        <div
          key={run.id}
          data-seeded="true"
          className="flex items-center justify-between rounded-lg border border-border p-4"
        >
          <div className="flex-1">
            <p className="text-sm font-medium">
              {run.input_text
                ? run.input_text.slice(0, 80) + (run.input_text.length > 80 ? "..." : "")
                : "File upload"}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {new Date(run.created_at).toLocaleString()} &middot;{" "}
              {run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : "—"} &middot;{" "}
              {run.tokens_used} tokens
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Badge
              variant={
                run.status === "completed"
                  ? "default"
                  : run.status === "failed"
                    ? "destructive"
                    : "secondary"
              }
            >
              {run.status}
            </Badge>
            <Link
              href={`/dashboard/traces/${run.id}`}
              className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            >
              Trace →
            </Link>
          </div>
        </div>
      ))}
    </div>
  );
}
