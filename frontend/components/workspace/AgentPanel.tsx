"use client";

import { useEffect, useState } from "react";
import { getToken } from "@/lib/auth-client";
import { api } from "@/lib/api";
import { isDemoMode } from "@/lib/demo-data";
import type { FileChangeEvent } from "@/lib/workspace-ws";
import { Clock, FileEdit, FileOutput, Cpu } from "lucide-react";

interface AgentActivity {
  id: string;
  type: string;
  path: string;
  attribution: string;
  timestamp: string;
}

interface AgentPanelProps {
  workspaceId: string;
  recentChanges?: FileChangeEvent[];
}

export function AgentPanel({ workspaceId, recentChanges = [] }: AgentPanelProps) {
  const [history, setHistory] = useState<AgentActivity[]>([]);

  useEffect(() => {
    if (isDemoMode()) {
      setHistory([
        { id: "1", type: "modify", path: "src/app.py", attribution: "agent:research-bot", timestamp: "2 min ago" },
        { id: "2", type: "create", path: "output/report.md", attribution: "agent:doc-writer", timestamp: "5 min ago" },
        { id: "3", type: "modify", path: "config.json", attribution: "user:web", timestamp: "10 min ago" },
      ]);
      return;
    }

    async function loadHistory() {
      const token = await getToken();
      if (!token) return;
      try {
        const data = await api.workspaces.history(workspaceId, token);
        setHistory(
          (data as { id: string; change_type: string; file_path: string; attribution: string; created_at: string }[]).slice(0, 20).map((d) => ({
            id: d.id,
            type: d.change_type,
            path: d.file_path,
            attribution: d.attribution,
            timestamp: formatTime(d.created_at),
          }))
        );
      } catch {
        // ignore
      }
    }
    loadHistory();
    const interval = setInterval(loadHistory, 10000);
    return () => clearInterval(interval);
  }, [workspaceId]);

  function getIcon(type: string) {
    if (type === "create") return <FileOutput className="h-3.5 w-3.5 text-green-400" />;
    if (type === "delete") return <FileEdit className="h-3.5 w-3.5 text-red-400" />;
    return <FileEdit className="h-3.5 w-3.5 text-blue-400" />;
  }

  function getAttributionBadge(attr: string) {
    if (attr.startsWith("agent:")) {
      return <span className="rounded bg-purple-900/50 px-1 py-0.5 text-[10px] text-purple-300">agent</span>;
    }
    if (attr.startsWith("blueprint:")) {
      return <span className="rounded bg-blue-900/50 px-1 py-0.5 text-[10px] text-blue-300">blueprint</span>;
    }
    if (attr === "user:web") {
      return <span className="rounded bg-green-900/50 px-1 py-0.5 text-[10px] text-green-300">web</span>;
    }
    if (attr === "user:neovim") {
      return <span className="rounded bg-amber-900/50 px-1 py-0.5 text-[10px] text-amber-300">nvim</span>;
    }
    return <span className="rounded bg-gray-800 px-1 py-0.5 text-[10px] text-gray-400">{attr}</span>;
  }

  const allActivity = [
    ...recentChanges.map((c, i) => ({
      id: `live-${i}`,
      type: c.change_type,
      path: c.path,
      attribution: c.source ?? "external",
      timestamp: "just now",
    })),
    ...history,
  ];

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 text-xs font-medium text-muted-foreground uppercase tracking-wider border-b border-border flex items-center gap-1.5">
        <Cpu className="h-3.5 w-3.5" />
        Activity
      </div>

      <div className="flex-1 overflow-y-auto">
        {allActivity.length === 0 ? (
          <p className="px-3 py-8 text-center text-xs text-muted-foreground">
            No activity yet. Changes by agents and users will appear here.
          </p>
        ) : (
          <div className="divide-y divide-border">
            {allActivity.map((item) => (
              <div key={item.id} className="px-3 py-2 hover:bg-accent/50">
                <div className="flex items-center gap-1.5">
                  {getIcon(item.type)}
                  <span className="text-xs truncate flex-1" title={item.path}>
                    {item.path}
                  </span>
                  {getAttributionBadge(item.attribution)}
                </div>
                <div className="flex items-center gap-1 mt-0.5 text-[10px] text-muted-foreground">
                  <Clock className="h-2.5 w-2.5" />
                  {item.timestamp}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  if (diff < 60000) return "just now";
  if (diff < 3600000) return `${Math.floor(diff / 60000)} min ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return date.toLocaleDateString();
}
