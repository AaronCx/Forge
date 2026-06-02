"use client";

import { useState, type KeyboardEvent } from "react";
import Link from "next/link";
import { ArrowRight, Loader2, Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { Attachment, CatalogEntry } from "@/lib/api";

export interface ThreadState {
  status: "idle" | "routing" | "running" | "clarify" | "none" | "error" | "done";
  message: string; // the user's submitted message
  attachments?: Attachment[];
  target?: { type: "agent" | "blueprint"; id: string } | null;
  rationale?: string;
  routingCost?: number;
  coldStart?: boolean;
  steps: string[];
  output: string;
  runId?: string | null;
  clarifyQuestion?: string;
  threadId?: string | null;
  errorText?: string;
  noneMessage?: string;
}

interface DispatchThreadProps {
  thread: ThreadState | null;
  onClarifyReply: (reply: string, threadId: string | null | undefined) => void;
  onOverride: (targetType: "agent" | "blueprint", targetId: string) => void;
  targets: CatalogEntry[];
  busy: boolean;
}

function formatCost(cost?: number): string {
  if (!cost || cost <= 0) return "free";
  return `$${cost.toFixed(4)}`;
}

/**
 * Renders a single dispatch turn: the routing decision, live step/token
 * output, and a link to the full run — plus clarify / none / error states.
 */
export function DispatchThread({ thread, onClarifyReply, onOverride, targets, busy }: DispatchThreadProps) {
  const [reply, setReply] = useState("");

  if (!thread) return null;

  const handleOverridePick = (value: string) => {
    if (!value) return;
    const [type, id] = value.split(":");
    if (type === "agent" || type === "blueprint") onOverride(type, id);
  };

  // Once a turn has settled, let the user re-run against a different target.
  const showOverride =
    targets.length > 0 && ["done", "error", "none", "clarify"].includes(thread.status);

  const handleReplyKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const r = reply.trim();
      if (!r) return;
      onClarifyReply(r, thread.threadId);
      setReply("");
    }
  };

  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm" data-testid="dispatch-thread">
      {/* The user's message */}
      <p className="text-sm text-muted-foreground">
        <span className="font-medium text-foreground">You:</span> {thread.message}
      </p>

      {/* Attachments on the user's turn */}
      {thread.attachments && thread.attachments.length > 0 && (
        <ul className="mt-1 flex flex-wrap gap-2">
          {thread.attachments.map((a, i) => (
            <li
              key={`${a.name}-${i}`}
              className="flex items-center gap-1 rounded border bg-muted px-2 py-0.5 text-xs text-muted-foreground"
            >
              <Paperclip className="h-3 w-3" />
              <span className="max-w-[180px] truncate">{a.name}</span>
            </li>
          ))}
        </ul>
      )}

      {/* Routing header */}
      {(thread.status === "routing" || thread.target) && (
        <div className="mt-3 flex items-start gap-2 text-sm">
          {thread.status === "routing" ? (
            <span className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Routing…
            </span>
          ) : (
            <span className="flex flex-wrap items-center gap-1">
              <span className="text-muted-foreground">Routing</span>
              <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="rounded bg-accent px-1.5 py-0.5 font-medium capitalize">
                {thread.target?.type}: {thread.target?.id?.slice(0, 8)}
              </span>
              {thread.rationale && (
                <span className="text-muted-foreground">— {thread.rationale}</span>
              )}
              {thread.routingCost !== undefined && (
                <span className="text-muted-foreground/70">· routing {formatCost(thread.routingCost)}</span>
              )}
            </span>
          )}
        </div>
      )}

      {/* Step log */}
      {thread.steps.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
          {thread.steps.map((s, i) => (
            <li key={i} className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50" />
              {s}
            </li>
          ))}
        </ul>
      )}

      {/* Streamed output */}
      {thread.output && (
        <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-sm">
          {thread.output}
        </pre>
      )}

      {/* Running indicator */}
      {thread.status === "running" && (
        <p className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Running…
        </p>
      )}

      {/* Clarify */}
      {thread.status === "clarify" && (
        <div className="mt-3 space-y-2">
          <p className="text-sm">{thread.clarifyQuestion}</p>
          <div className="flex gap-2">
            <Textarea
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              onKeyDown={handleReplyKey}
              rows={1}
              placeholder="Reply…"
              className="min-h-[40px] resize-none"
              aria-label="Clarify reply"
            />
            <Button
              type="button"
              disabled={busy || !reply.trim()}
              onClick={() => {
                onClarifyReply(reply.trim(), thread.threadId);
                setReply("");
              }}
            >
              Reply
            </Button>
          </div>
        </div>
      )}

      {/* No match / cold start — offer to create an agent, prefilled from the message */}
      {thread.status === "none" && (
        <div className="mt-3 rounded-lg border border-dashed p-3">
          <p className="text-sm font-medium">
            {thread.coldStart ? "No agents yet" : "No agent fits this yet"}
          </p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {thread.noneMessage || "Nothing in your catalog matched this task."}
          </p>
          <Link href={`/dashboard/agents/new?prompt=${encodeURIComponent(thread.message)}`} className="mt-2 inline-block">
            <Button size="sm">Create an agent</Button>
          </Link>
        </div>
      )}

      {/* Error */}
      {thread.status === "error" && (
        <p className="mt-3 text-sm text-destructive">{thread.errorText || "Something went wrong."}</p>
      )}

      {/* Done — link to the run in the Operations workspace. There is no
          per-run detail route, so we deep-link to Operations (the run shows in
          its list) rather than a 404. */}
      {thread.status === "done" && thread.runId && (
        <div className="mt-3 flex items-center gap-3">
          <span className="text-xs text-muted-foreground">Run {thread.runId.slice(0, 8)}</span>
          <Link href="/dashboard/ops" className="text-sm font-medium text-primary hover:underline">
            View in Operations →
          </Link>
        </div>
      )}

      {/* Wrong target? Re-run against a specific agent/blueprint. */}
      {showOverride && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t pt-3 text-xs text-muted-foreground">
          <span>Wrong target?</span>
          <select
            aria-label="Re-run with a different target"
            className="rounded-md border bg-background px-2 py-1 text-foreground"
            disabled={busy}
            defaultValue=""
            onChange={(e) => {
              handleOverridePick(e.target.value);
              e.target.value = "";
            }}
          >
            <option value="" disabled>
              Re-run with…
            </option>
            {targets.map((t) => (
              <option key={`${t.type}:${t.id}`} value={`${t.type}:${t.id}`}>
                {t.name} ({t.type})
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
