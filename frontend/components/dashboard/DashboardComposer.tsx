"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Attachment, type CatalogEntry, type DispatchEvent } from "@/lib/api";
import { getToken } from "@/lib/auth-client";
import { isDemoMode } from "@/lib/demo-data";
import { Composer } from "./Composer";
import { DispatchThread, type ThreadState } from "./DispatchThread";

interface Override {
  type: "agent" | "blueprint";
  id: string;
}

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
  const [targets, setTargets] = useState<CatalogEntry[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const demo = typeof window !== "undefined" && isDemoMode();

  // Load the user's agents/blueprints once, for the override picker.
  useEffect(() => {
    if (demo) return;
    let cancelled = false;
    (async () => {
      const token = await getToken();
      if (!token) return;
      try {
        const t = await api.dispatch.targets(token);
        if (!cancelled) setTargets(t);
      } catch {
        // Non-fatal — the override picker just won't show.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [demo]);

  const runDispatch = useCallback(async (
    message: string,
    threadId: string,
    attachments: Attachment[] = [],
    override?: Override,
  ) => {
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
    setThread({ status: "routing", message, steps: [], output: "", threadId, attachments });

    const controller = new AbortController();
    abortRef.current = controller;

    const onEvent = (event: DispatchEvent) => {
      setThread((prev) => {
        if (!prev) return prev;
        switch (event.type) {
          case "routing":
            return {
              ...prev,
              status: "running",
              target: event.target,
              rationale: event.rationale,
              routingCost: event.routing_cost,
            };
          case "step":
            return { ...prev, status: "running", steps: [...prev.steps, stepText(event.data)] };
          case "token":
            return { ...prev, status: "running", output: prev.output + event.data };
          case "clarify":
            return { ...prev, status: "clarify", clarifyQuestion: event.question, threadId: event.thread_id ?? prev.threadId };
          case "none":
            return { ...prev, status: "none", noneMessage: event.message, coldStart: event.cold_start };
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
      await api.dispatch.send(
        {
          message,
          thread_id: threadId,
          attachments,
          ...(override ? { target_type: override.type, target_id: override.id } : {}),
        },
        token,
        onEvent,
        controller.signal,
      );
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
    async (message: string, files: File[]) => {
      const threadId = newThreadId();
      if (files.length === 0) {
        void runDispatch(message, threadId);
        return;
      }

      if (demo) {
        setThread({
          status: "error",
          message,
          steps: [],
          output: "",
          errorText: "Uploads are disabled in demo mode.",
        });
        return;
      }

      const token = await getToken();
      if (!token) {
        setThread({ status: "error", message, steps: [], output: "", errorText: "Not authenticated." });
        return;
      }

      // Upload first, then dispatch with the returned refs.
      setBusy(true);
      setThread({ status: "routing", message, steps: ["Uploading attachments…"], output: "", threadId });
      try {
        const attachments = await api.uploads.files(files, token);
        await runDispatch(message, threadId, attachments);
      } catch (err) {
        setBusy(false);
        setThread({
          status: "error",
          message,
          steps: [],
          output: "",
          errorText: err instanceof Error ? err.message : "Upload failed.",
        });
      }
    },
    [runDispatch, demo],
  );

  const handleTranscribe = useCallback(async (blob: Blob): Promise<string> => {
    const token = await getToken();
    if (!token) throw new Error("Not authenticated.");
    return api.transcribe.send(blob, token);
  }, []);

  const handleClarifyReply = useCallback(
    (reply: string, threadId: string | null | undefined) => {
      const original = thread?.message ? `${thread.message}\n\n${reply}` : reply;
      void runDispatch(original, threadId || newThreadId());
    },
    [runDispatch, thread?.message],
  );

  const handleOverride = useCallback(
    (targetType: "agent" | "blueprint", targetId: string) => {
      if (!thread) return;
      void runDispatch(thread.message, newThreadId(), thread.attachments ?? [], { type: targetType, id: targetId });
    },
    [runDispatch, thread],
  );

  return (
    <section className="space-y-3" aria-label="Command composer">
      <Composer
        onSend={handleSend}
        onTranscribe={demo ? undefined : handleTranscribe}
        busy={busy}
        disabled={demo}
      />
      <DispatchThread
        thread={thread}
        onClarifyReply={handleClarifyReply}
        onOverride={handleOverride}
        targets={targets}
        busy={busy}
      />
    </section>
  );
}
