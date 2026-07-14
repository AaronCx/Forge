"use client";

import { useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";
import { API_URL } from "@/lib/constants";
import { isDemoMode } from "@/lib/demo-data";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";

type ModelCard = { id: string; provider: string; display_name: string; vision: boolean; tools: boolean };
type Turn = { role: "user" | "assistant"; text: string; tools: string[] };

export default function ChatPage() {
  const [demo, setDemo] = useState(false);
  const [models, setModels] = useState<ModelCard[]>([]);
  const [model, setModel] = useState("");
  const [sessionId, setSessionId] = useState<string>("");
  const [turns, setTurns] = useState<Turn[]>([]);
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
  }, [turns]);

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
      body: JSON.stringify({ title: "Chat", model }),
    });
    const session = await res.json();
    setSessionId(session.id);
    return session.id;
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    const t = await token();
    if (!t) return;
    setInput("");
    setBusy(true);
    setTurns((prev) => [...prev, { role: "user", text, tools: [] }, { role: "assistant", text: "", tools: [] }]);

    try {
      const id = await ensureSession(t);
      const res = await fetch(`${API_URL}/api/sessions/${id}/messages`, {
        method: "POST",
        headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json" },
        body: JSON.stringify({ text, model }),
      });
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
            const event = JSON.parse(data);
            setTurns((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (event.type === "token") last.text += event.data;
              else if (event.type === "tool_use") last.tools.push(`→ ${event.data?.name}`);
              else if (event.type === "tool_result") {
                const mark = event.data?.is_error ? "✗" : "✓";
                last.tools.push(`${mark} ${event.data?.tool}`);
              }
              return next;
            });
          } catch {
            // skip malformed frame
          }
        }
      }
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

      <div className="mt-4 flex-1 space-y-3 overflow-y-auto">
        {turns.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Start a conversation. Your message runs against the selected model with
            the full tool plane available; approvals appear in the Approvals inbox.
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
