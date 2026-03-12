"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { api, MCPConnection } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { isDemoMode } from "@/lib/demo-data";

const STATUS_COLORS: Record<string, string> = {
  connected: "bg-green-500",
  disconnected: "bg-yellow-500",
  error: "bg-red-500",
};

const DEMO_CONNECTIONS: MCPConnection[] = [
  {
    id: "demo-mcp-1",
    name: "GitHub MCP",
    server_url: "https://mcp.github.example.com",
    status: "connected",
    tools_discovered: [
      { name: "list_repos", description: "List repositories", input_schema: {} },
      { name: "create_pr", description: "Create a pull request", input_schema: {} },
    ],
    created_at: "2026-03-10T10:00:00Z",
    last_connected_at: "2026-03-12T12:00:00Z",
  },
];

export function MCPManager() {
  const [connections, setConnections] = useState<MCPConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [testing, setTesting] = useState<string | null>(null);

  useEffect(() => {
    if (isDemoMode()) {
      setConnections(DEMO_CONNECTIONS);
      setLoading(false);
      return;
    }
    loadConnections();
  }, []);

  async function loadConnections() {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      const conns = await api.mcp.connections(data.session.access_token);
      setConnections(conns);
    } catch {
      // API may not be running
    } finally {
      setLoading(false);
    }
  }

  async function addConnection() {
    if (!name.trim() || !url.trim()) return;
    setError("");
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      await api.mcp.connect({ name, server_url: url }, data.session.access_token);
      setName("");
      setUrl("");
      setShowAdd(false);
      await loadConnections();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect");
    }
  }

  async function testConnection(id: string) {
    setTesting(id);
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      await api.mcp.testConnection(id, data.session.access_token);
      await loadConnections();
    } catch {
      // ignore
    } finally {
      setTesting(null);
    }
  }

  async function deleteConnection(id: string) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      await api.mcp.deleteConnection(id, data.session.access_token);
      setConnections(connections.filter((c) => c.id !== id));
    } catch {
      // ignore
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">MCP Connections</h2>
        <Button variant="outline" size="sm" onClick={() => setShowAdd(!showAdd)}>
          {showAdd ? "Cancel" : "Add Server"}
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {showAdd && (
        <div className="rounded-lg border border-border p-4 space-y-3">
          <Input
            placeholder="Connection name (e.g., GitHub MCP)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Input
            placeholder="Server URL (e.g., http://localhost:3100)"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <Button onClick={addConnection} disabled={!name.trim() || !url.trim()}>
            Connect
          </Button>
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {[1, 2].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : connections.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No MCP servers connected. Add one to give agents access to external tools.
        </p>
      ) : (
        <div className="space-y-3">
          {connections.map((conn) => (
            <div
              key={conn.id}
              className="flex items-center gap-3 rounded-lg border border-border p-4"
            >
              <div
                className={`h-2.5 w-2.5 rounded-full ${STATUS_COLORS[conn.status] || STATUS_COLORS.error}`}
              />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{conn.name}</span>
                  <Badge variant="outline">
                    {conn.tools_discovered.length} tools
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground">{conn.server_url}</p>
                {conn.tools_discovered.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {conn.tools_discovered.slice(0, 5).map((t) => (
                      <Badge key={t.name} variant="secondary" className="text-xs">
                        {t.name}
                      </Badge>
                    ))}
                    {conn.tools_discovered.length > 5 && (
                      <span className="text-xs text-muted-foreground">
                        +{conn.tools_discovered.length - 5} more
                      </span>
                    )}
                  </div>
                )}
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => testConnection(conn.id)}
                  disabled={testing === conn.id}
                >
                  {testing === conn.id ? "Testing..." : "Test"}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive"
                  onClick={() => deleteConnection(conn.id)}
                >
                  Remove
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
