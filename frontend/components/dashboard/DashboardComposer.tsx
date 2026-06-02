"use client";

import { useCallback, useRef, useState } from "react";
import { api, type DispatchEvent } from "@/lib/api";
import { getToken } from "@/lib/auth-client";
import { isDemoMode } from "@/lib/demo-data";
import { Composer } from "./Composer";
import { DispatchThread, type ThreadState } from "./DispatchThread";

function newThreadId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `th-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

function stepText(data: { step: number; result: string } | string): string {
  if (typeof data === "string") return data;
  return data.result || `Step ${data.step}`;
}

/**
 * Owns the dispatch turn: sends the message to /api/dispatch, consumes the
 * typed SSE events, and feeds <Composer/> + <DispatchThread/>. Routed runs go
 * through the normal run path, so the metric sections below refresh on their
 * own existing stream.
 */
export function DashboardComposer() {
  const [thread, setThread] = useState<ThreadState | null>(null);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const demo = typeof window !== "undefined" && isDemoMode();

  const runDispatch = useCallback(async (message: string, threadId: string) => {
    if (demo) {
      setThread({
        status: "error",
        message,
        steps: [],
        output: "",
        errorText: "Dispatch is disabled in demo mode — connect a backend to route tasks.",
      });
      return;
    }

    const token = await getToken();
    if (!token) {
      setThread({ status: "error", message, steps: [], output: "", errorText: "Not authenticated." });
      return;
    }

    setBusy(true);
    setThread({ status: "routing", message, steps: [], output: "", threadId });

    const controller = new AbortController();
    abortRef.current = controller;

    const onEvent = (event: DispatchEvent) => {
      setThread((prev) => {
        if (!prev) return prev;
        switch (event.type) {
          case "routing":
            return { ...prev, status: "running", target: event.target, rationale: event.rationale };
          case "step":
            return { ...prev, status: "running", steps: [...prev.steps, stepText(event.data)] };
          case "token":
            return { ...prev, status: "running", output: prev.output + event.data };
          case "clarify":
            return { ...prev, status: "clarify", clarifyQuestion: event.question, threadId: event.thread_id ?? prev.threadId };
          case "none":
            return { ...prev, status: "none", noneMessage: event.message };
          case "done":
            return { ...prev, status: "done", runId: event.run_id };
          case "error":
            return { ...prev, status: "error", errorText: event.data };
          default:
            return prev;
        }
      });
    };

    try {
      await api.dispatch.send({ message, thread_id: threadId }, token, onEvent, controller.signal);
    } catch (err) {
      if (err instanceof Error && err.name !== "AbortError") {
        setThread((prev) =>
          prev ? { ...prev, status: "error", errorText: err.message } : prev,
        );
      }
    } finally {
      setBusy(false);
    }
  }, [demo]);

  const handleSend = useCallback(
    (message: string) => {
      void runDispatch(message, newThreadId());
    },
    [runDispatch],
  );

  const handleClarifyReply = useCallback(
    (reply: string, threadId: string | null | undefined) => {
      const original = thread?.message ? `${thread.message}\n\n${reply}` : reply;
      void runDispatch(original, threadId || newThreadId());
    },
    [runDispatch, thread?.message],
  );

  return (
    <section className="space-y-3" aria-label="Command composer">
      <Composer onSend={handleSend} busy={busy} disabled={demo} />
      <DispatchThread thread={thread} onClarifyReply={handleClarifyReply} busy={busy} />
    </section>
  );
}
