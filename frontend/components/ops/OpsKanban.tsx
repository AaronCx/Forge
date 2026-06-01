"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCircle2, Loader2, PauseCircle, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { api, type Approval, type Run } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { DEMO_RUNS, isDemoMode } from "@/lib/demo-data";

type OpsColumn = "queued" | "running" | "awaiting-approval" | "done" | "failed";

const COLUMNS: { id: OpsColumn; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "queued", label: "Queued", icon: PauseCircle },
  { id: "running", label: "Running", icon: Loader2 },
  { id: "awaiting-approval", label: "Awaiting Approval", icon: PauseCircle },
  { id: "done", label: "Done", icon: CheckCircle2 },
  { id: "failed", label: "Failed", icon: XCircle },
];

/**
 * PR-5 Operations kanban. Each run is a card; columns are lifecycle stages.
 * Approvals slot into the "Awaiting Approval" column alongside any runs whose
 * agents have pending HITL prompts. Polling-based refresh every 5s — the spec
 * calls for a WebSocket upgrade once the existing run-events stream is wired
 * up; the polling here is a placeholder that produces the same UX at slightly
 * worse latency.
 *
 * Clicking a card opens the existing run/approval detail page; a future PR
 * will inline a right-side drawer to match the design exactly.
 */
export function OpsKanban() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (isDemoMode()) {
        setRuns(DEMO_RUNS);
        setApprovals([]);
        setLoaded(true);
        return;
      }
      const { data } = await supabase.auth.getSession();
      if (!data.session) {
        setLoaded(true);
        return;
      }
      try {
        const [runList, approvalList] = await Promise.all([
          api.runs.list(data.session.access_token),
          api.approvals.list("pending", data.session.access_token).catch(() => [] as Approval[]),
        ]);
        if (cancelled) return;
        setRuns(runList);
        setApprovals(approvalList);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load operations");
      } finally {
        if (!cancelled) setLoaded(true);
      }
    }

    load();
    const interval = setInterval(load, 5_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const byColumn: Record<OpsColumn, Array<{ id: string; type: "run" | "approval"; data: Run | Approval }>> = {
    queued: [],
    running: [],
    "awaiting-approval": [],
    done: [],
    failed: [],
  };

  for (const r of runs) {
    const col = mapRunStatus(r.status);
    byColumn[col].push({ id: r.id, type: "run", data: r });
  }
  for (const a of approvals) {
    byColumn["awaiting-approval"].push({ id: a.id, type: "approval", data: a });
  }

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="grid auto-rows-min gap-3 lg:grid-cols-5">
        {COLUMNS.map((col) => {
          const cards = byColumn[col.id];
          const Icon = col.icon;
          return (
            <div
              key={col.id}
              data-column={col.id}
              className="flex flex-col gap-2 rounded-lg border bg-card/40 p-2"
            >
              <div className="flex items-center justify-between gap-2 px-2 pt-1">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <Icon className={cn("h-4 w-4", col.id === "running" && "animate-spin")} aria-hidden />
                  {col.label}
                </div>
                <Badge variant="outline" className="font-mono text-[10px]">
                  {cards.length}
                </Badge>
              </div>

              <div className="flex flex-col gap-2">
                {!loaded ? (
                  <div className="h-16 animate-pulse rounded-md bg-muted/40" />
                ) : cards.length === 0 ? (
                  <p className="px-2 py-3 text-xs text-muted-foreground">No cards</p>
                ) : (
                  cards.map((card) =>
                    card.type === "run" ? (
                      <RunCard key={card.id} run={card.data as Run} />
                    ) : (
                      <ApprovalCard key={card.id} approval={card.data as Approval} />
                    ),
                  )
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function RunCard({ run }: { run: Run }) {
  return (
    <Link
      href={`/dashboard/runs/${run.id}`}
      className="block rounded-md border bg-background p-2 text-left transition hover:border-foreground/30"
      data-run-id={run.id}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="font-mono text-[10px] text-muted-foreground">{run.id.slice(0, 8)}</div>
        {run.tokens_used > 0 && (
          <div className="text-[10px] text-muted-foreground">{run.tokens_used.toLocaleString()} tok</div>
        )}
      </div>
      <div className="mt-1 line-clamp-2 text-xs">
        {run.input_text || run.output || "—"}
      </div>
      <div className="mt-1 text-[10px] text-muted-foreground">
        {new Date(run.created_at).toLocaleString()}
      </div>
    </Link>
  );
}

function ApprovalCard({ approval }: { approval: Approval }) {
  return (
    <div
      className="rounded-md border border-yellow-500/40 bg-yellow-500/5 p-2"
      data-approval-id={approval.id}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="font-mono text-[10px] text-yellow-700 dark:text-yellow-300">
          {approval.id.slice(0, 8)}
        </div>
      </div>
      <div className="mt-1 text-xs">
        Approval pending on run{" "}
        <span className="font-mono">{approval.blueprint_run_id.slice(0, 8)}</span>
      </div>
      <div className="mt-2 flex gap-1.5">
        <Button asChild size="sm" variant="default" className="h-6 px-2 text-[10px]">
          <Link href={`/dashboard/approvals?id=${approval.id}`}>Review</Link>
        </Button>
      </div>
    </div>
  );
}

function mapRunStatus(status: Run["status"]): OpsColumn {
  switch (status) {
    case "pending":
      return "queued";
    case "running":
      return "running";
    case "completed":
      return "done";
    case "failed":
      return "failed";
  }
}
