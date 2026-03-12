"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { supabase } from "@/lib/supabase";
import { api, Agent } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StreamingOutput } from "./StreamingOutput";
import { StepLog } from "./StepLog";
import { FileUploader } from "./FileUploader";

interface RunnerPanelProps {
  agent: Agent;
}

interface LogEntry {
  type: string;
  data: string | { step: number; result: string; duration_ms?: number };
}

export function RunnerPanel({ agent }: RunnerPanelProps) {
  const [input, setInput] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [output, setOutput] = useState("");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const runAgent = useCallback(async () => {
    setRunning(true);
    setOutput("");
    setLogs([]);
    setError("");

    const { data } = await supabase.auth.getSession();
    if (!data.session) {
      setError("Not authenticated");
      setRunning(false);
      return;
    }

    const url = api.runs.start(agent.id, { text: input }, data.session.access_token);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(url, { method: "POST", signal: controller.signal });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: "Run failed" }));
        setError(err.detail || "Run failed");
        setRunning(false);
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        setError("No response stream");
        setRunning(false);
        return;
      }

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
            const event = JSON.parse(data);

            if (event.type === "step") {
              setLogs((prev) => [...prev, { type: "step", data: event.data }]);
            } else if (event.type === "token") {
              setOutput((prev) => prev + event.data);
            } else if (event.type === "tool_call") {
              setLogs((prev) => [
                ...prev,
                { type: "tool", data: `Tool: ${event.data?.tool || "unknown"}` },
              ]);
            } else if (event.type === "error") {
              setError(event.data);
            } else if (event.type === "done") {
              setLogs((prev) => [...prev, { type: "done", data: "Completed" }]);
            }
          } catch {
            // Skip malformed events
          }
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name !== "AbortError") {
        setError(err.message);
      }
    } finally {
      setRunning(false);
    }
  }, [agent.id, input]);

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !running && (input.trim() || file)) {
              e.preventDefault();
              runAgent();
            }
          }}
          placeholder="Enter your input for the agent... (Ctrl+Enter to run)"
          rows={4}
        />
        <div className="flex items-center gap-3">
          <FileUploader onFileSelect={setFile} selectedFile={file} />
          <div className="flex-1" />
          <Button onClick={runAgent} disabled={running || (!input.trim() && !file)}>
            {running ? "Running..." : "Run Agent"}
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <Tabs defaultValue="output">
        <TabsList>
          <TabsTrigger value="output">Output</TabsTrigger>
          <TabsTrigger value="logs">
            Step Logs ({logs.length})
          </TabsTrigger>
        </TabsList>
        <TabsContent value="output" className="mt-4">
          <StreamingOutput content={output} />
        </TabsContent>
        <TabsContent value="logs" className="mt-4">
          <StepLog logs={logs} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
