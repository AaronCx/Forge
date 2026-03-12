"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { api, Trigger, TriggerHistory, Agent, Blueprint } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { isDemoMode } from "@/lib/demo-data";

const DEMO_TRIGGERS: Trigger[] = [
  {
    id: "demo-trigger-1",
    user_id: "demo",
    type: "webhook",
    config: { webhook_secret: "abc123" },
    target_type: "blueprint",
    target_id: "demo-bp-1",
    enabled: true,
    last_fired_at: "2026-03-12T10:00:00Z",
    fire_count: 12,
    created_at: "2026-03-10T10:00:00Z",
  },
  {
    id: "demo-trigger-2",
    user_id: "demo",
    type: "cron",
    config: { cron_expression: "0 9 * * *" },
    target_type: "agent",
    target_id: "demo-1",
    enabled: true,
    last_fired_at: "2026-03-12T09:00:00Z",
    fire_count: 3,
    created_at: "2026-03-11T09:00:00Z",
  },
];

export default function TriggersPage() {
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [blueprints, setBlueprints] = useState<Blueprint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  // Create form state
  const [newType, setNewType] = useState<"webhook" | "cron" | "mcp_event">("webhook");
  const [newTargetType, setNewTargetType] = useState<"agent" | "blueprint">("agent");
  const [newTargetId, setNewTargetId] = useState("");
  const [newCronExpr, setNewCronExpr] = useState("0 * * * *");

  // History state
  const [historyTriggerId, setHistoryTriggerId] = useState<string | null>(null);
  const [history, setHistory] = useState<TriggerHistory[]>([]);

  useEffect(() => {
    if (isDemoMode()) {
      setTriggers(DEMO_TRIGGERS);
      setLoading(false);
      return;
    }
    loadData();
  }, []);

  async function loadData() {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      const [triggerList, agentList, bpList] = await Promise.all([
        api.triggers.list(data.session.access_token),
        api.agents.list(data.session.access_token),
        api.blueprints.list(data.session.access_token),
      ]);
      setTriggers(triggerList);
      setAgents(agentList);
      setBlueprints(bpList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load triggers");
    } finally {
      setLoading(false);
    }
  }

  async function createTrigger() {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    const config: Record<string, unknown> = {};
    if (newType === "cron") config.cron_expression = newCronExpr;

    try {
      await api.triggers.create(
        {
          type: newType,
          config,
          target_type: newTargetType,
          target_id: newTargetId,
        },
        data.session.access_token
      );
      setShowCreate(false);
      setNewTargetId("");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create trigger");
    }
  }

  async function toggleTrigger(id: string) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      await api.triggers.toggle(id, data.session.access_token);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to toggle trigger");
    }
  }

  async function deleteTrigger(id: string) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      await api.triggers.delete(id, data.session.access_token);
      setTriggers(triggers.filter((t) => t.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete trigger");
    }
  }

  async function viewHistory(triggerId: string) {
    if (isDemoMode()) {
      setHistoryTriggerId(triggerId);
      setHistory([]);
      return;
    }
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      const hist = await api.triggers.history(triggerId, data.session.access_token);
      setHistory(hist);
      setHistoryTriggerId(triggerId);
    } catch {
      // ignore
    }
  }

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const targetOptions = newTargetType === "agent" ? agents : blueprints;

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Triggers</h1>
          <p className="mt-1 text-muted-foreground">
            Automate agent and blueprint runs with webhooks, schedules, and events
          </p>
        </div>
        <Button onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? "Cancel" : "New Trigger"}
        </Button>
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {showCreate && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Create Trigger</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="text-sm font-medium">Type</label>
                <select
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  value={newType}
                  onChange={(e) => setNewType(e.target.value as typeof newType)}
                >
                  <option value="webhook">Webhook</option>
                  <option value="cron">Cron / Schedule</option>
                  <option value="mcp_event">MCP Event</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium">Target</label>
                <select
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  value={newTargetType}
                  onChange={(e) => {
                    setNewTargetType(e.target.value as typeof newTargetType);
                    setNewTargetId("");
                  }}
                >
                  <option value="agent">Agent</option>
                  <option value="blueprint">Blueprint</option>
                </select>
              </div>
            </div>

            <div>
              <label className="text-sm font-medium">
                {newTargetType === "agent" ? "Agent" : "Blueprint"}
              </label>
              <select
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                value={newTargetId}
                onChange={(e) => setNewTargetId(e.target.value)}
              >
                <option value="">Select...</option>
                {targetOptions.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>

            {newType === "cron" && (
              <div>
                <label className="text-sm font-medium">Cron Expression</label>
                <Input
                  className="mt-1"
                  placeholder="0 * * * * (every hour)"
                  value={newCronExpr}
                  onChange={(e) => setNewCronExpr(e.target.value)}
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Common: <code>0 * * * *</code> (hourly), <code>0 9 * * *</code> (daily 9am),{" "}
                  <code>0 9 * * 1</code> (weekly Monday)
                </p>
              </div>
            )}

            <Button onClick={createTrigger} disabled={!newTargetId}>
              Create Trigger
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="mt-6 space-y-4">
        {loading ? (
          <div className="space-y-3">
            {[1, 2].map((i) => (
              <div key={i} className="h-24 animate-pulse rounded-lg bg-muted" />
            ))}
          </div>
        ) : triggers.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No triggers yet. Create one to automate agent runs.
          </p>
        ) : (
          triggers.map((trigger) => (
            <Card key={trigger.id}>
              <CardContent className="flex items-center gap-4 py-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Badge variant={trigger.enabled ? "default" : "secondary"}>
                      {trigger.type}
                    </Badge>
                    <Badge variant="outline">{trigger.target_type}</Badge>
                    {!trigger.enabled && (
                      <Badge variant="secondary">Disabled</Badge>
                    )}
                  </div>
                  <p className="mt-1 text-sm">
                    Target: <span className="font-mono text-xs">{trigger.target_id.slice(0, 8)}...</span>
                  </p>
                  {trigger.type === "webhook" && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      URL: <code>{apiUrl}/api/webhooks/{trigger.id}</code>
                    </p>
                  )}
                  {trigger.type === "cron" && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      Schedule: <code>{String(trigger.config.cron_expression || "")}</code>
                    </p>
                  )}
                  <p className="mt-1 text-xs text-muted-foreground">
                    Fired {trigger.fire_count} times
                    {trigger.last_fired_at && (
                      <> &middot; Last: {new Date(trigger.last_fired_at).toLocaleString()}</>
                    )}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => viewHistory(trigger.id)}
                  >
                    History
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => toggleTrigger(trigger.id)}
                  >
                    {trigger.enabled ? "Disable" : "Enable"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive"
                    onClick={() => deleteTrigger(trigger.id)}
                  >
                    Delete
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {historyTriggerId && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              Trigger History
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setHistoryTriggerId(null)}
              >
                Close
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {history.length === 0 ? (
              <p className="text-sm text-muted-foreground">No firing history yet.</p>
            ) : (
              <div className="space-y-2">
                {history.map((h) => (
                  <div
                    key={h.id}
                    className="flex items-center justify-between rounded border border-border p-2 text-sm"
                  >
                    <div>
                      <Badge variant="outline">{h.status}</Badge>
                      <span className="ml-2 text-xs text-muted-foreground">
                        {new Date(h.created_at).toLocaleString()}
                      </span>
                    </div>
                    {h.run_id && (
                      <span className="font-mono text-xs text-muted-foreground">
                        Run: {h.run_id.slice(0, 8)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
