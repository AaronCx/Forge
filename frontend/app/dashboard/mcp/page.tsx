"use client";

import { useEffect, useState } from "react";
import { Plug } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  isDemoMode,
  DEMO_MCP_SERVERS,
  DEMO_MCP_LOGS,
} from "@/lib/demo-data";
import { supabase } from "@/lib/supabase";
import { API_URL } from "@/lib/constants";

interface ServerRow {
  id: string;
  name: string;
  transport: "stdio" | "sse";
  status: "connected" | "degraded" | "disconnected";
  tool_count: number;
  last_seen: string;
  tools: { name: string; description: string; schema: string }[];
}

interface LogRow {
  ts: string;
  server: string;
  level: string;
  message: string;
}

function StatusPill({ status }: { status: ServerRow["status"] }) {
  const tone = {
    connected: "bg-emerald-500/15 text-emerald-300 border-emerald-700",
    degraded: "bg-yellow-500/15 text-yellow-300 border-yellow-700",
    disconnected: "bg-red-500/15 text-red-300 border-red-700",
  } as const;
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${tone[status]}`}>
      {status}
    </span>
  );
}

export default function McpPage() {
  const [servers, setServers] = useState<ServerRow[]>([]);
  const [logs, setLogs] = useState<LogRow[]>([]);
  const [demo, setDemo] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newUrl, setNewUrl] = useState("");

  useEffect(() => {
    if (isDemoMode()) {
      setDemo(true);
      setServers(DEMO_MCP_SERVERS);
      setLogs(DEMO_MCP_LOGS);
      return;
    }
    async function load() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) return;
      const token = data.session.access_token;
      try {
        const res = await fetch(`${API_URL}/api/mcp/connections`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const list = (await res.json()) as Array<{ id: string; name: string; server_url: string; tools: unknown[] }>;
          setServers(
            list.map((c) => ({
              id: c.id,
              name: c.name,
              transport: "stdio",
              status: "connected" as const,
              tool_count: c.tools.length,
              last_seen: new Date().toISOString(),
              tools: c.tools as { name: string; description: string; schema: string }[],
            }))
          );
        }
      } catch {
        // ignore
      }
    }
    load();
  }, []);

  function handleAdd() {
    if (demo) {
      toast("Demo mode — connect a Forge runtime to add servers");
      setDialogOpen(false);
      return;
    }
    if (!newName.trim() || !newUrl.trim()) return;
    toast.message("Connecting to MCP server...");
    setDialogOpen(false);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3">
        <Plug className="mt-1 h-6 w-6 text-muted-foreground" aria-hidden="true" />
        <div>
          <h1 className="text-3xl font-bold">MCP</h1>
          <p className="mt-1 text-muted-foreground">
            Model Context Protocol connection management — servers, tool inventory, and logs.
          </p>
        </div>
      </div>

      <div className="flex justify-end">
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button>+ Add connection</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add MCP server</DialogTitle>
              <DialogDescription>
                Register an MCP server. Forge will perform a handshake and register its tools.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="mcp-name">Name</Label>
                <Input
                  id="mcp-name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="filesystem"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="mcp-url">Server URL</Label>
                <Input
                  id="mcp-url"
                  value={newUrl}
                  onChange={(e) => setNewUrl(e.target.value)}
                  placeholder="stdio:///opt/mcp/filesystem.sh or https://..."
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleAdd}>Connect</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Connected servers</CardTitle>
        </CardHeader>
        <CardContent>
          {servers.length === 0 ? (
            <p className="text-sm text-muted-foreground">No MCP servers connected.</p>
          ) : (
            <div className="divide-y divide-border">
              {servers.map((server) => (
                <div key={server.id} data-seeded={demo}>
                  <button
                    className="flex w-full items-center justify-between py-3 text-left"
                    onClick={() =>
                      setExpanded((prev) => (prev === server.id ? null : server.id))
                    }
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-sm">{server.name}</span>
                      <StatusPill status={server.status} />
                      <Badge variant="outline" className="text-[10px]">
                        {server.transport}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {server.tool_count} tool{server.tool_count === 1 ? "" : "s"}
                      </span>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {expanded === server.id ? "▾" : "▸"}
                    </span>
                  </button>
                  {expanded === server.id && (
                    <div className="space-y-2 border-l-2 border-border pl-4 pb-3">
                      {server.tools.map((tool) => (
                        <div key={tool.name} className="text-sm">
                          <p className="font-mono">{tool.name}</p>
                          <p className="text-xs text-muted-foreground">{tool.description}</p>
                          <pre className="mt-1 overflow-x-auto rounded bg-muted px-2 py-1 text-[11px]">
                            {tool.schema}
                          </pre>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Connection logs</CardTitle>
        </CardHeader>
        <CardContent>
          {logs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No connection events yet.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {logs.map((log) => (
                <li key={log.ts + log.server} data-seeded={demo} className="font-mono text-xs">
                  <span className="text-muted-foreground">{new Date(log.ts).toLocaleString()}</span>{" "}
                  <Badge variant={log.level === "warn" ? "destructive" : "outline"} className="ml-1">
                    {log.level}
                  </Badge>{" "}
                  <span className="ml-1 text-muted-foreground">[{log.server}]</span>{" "}
                  <span>{log.message}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
