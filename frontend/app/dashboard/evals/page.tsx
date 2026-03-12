"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { api, EvalSuite, EvalRun, Agent, Blueprint } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { isDemoMode } from "@/lib/demo-data";

export default function EvalsPage() {
  const [suites, setSuites] = useState<EvalSuite[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [blueprints, setBlueprints] = useState<Blueprint[]>([]);
  const [runs, setRuns] = useState<Record<string, EvalRun[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  // Create form
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newTargetType, setNewTargetType] = useState<"agent" | "blueprint">("agent");
  const [newTargetId, setNewTargetId] = useState("");

  // Run state
  const [running, setRunning] = useState<string | null>(null);

  useEffect(() => {
    if (isDemoMode()) {
      setSuites([]);
      setLoading(false);
      return;
    }
    loadData();
  }, []);

  async function loadData() {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      const [suiteList, agentList, bpList] = await Promise.all([
        api.evals.suites(data.session.access_token),
        api.agents.list(data.session.access_token),
        api.blueprints.list(data.session.access_token),
      ]);
      setSuites(suiteList);
      setAgents(agentList);
      setBlueprints(bpList);

      // Load runs for each suite
      const runsMap: Record<string, EvalRun[]> = {};
      for (const suite of suiteList) {
        try {
          runsMap[suite.id] = await api.evals.listRuns(suite.id, data.session.access_token);
        } catch {
          runsMap[suite.id] = [];
        }
      }
      setRuns(runsMap);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  async function createSuite() {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      await api.evals.createSuite(
        { name: newName, description: newDesc, target_type: newTargetType, target_id: newTargetId },
        data.session.access_token
      );
      setShowCreate(false);
      setNewName("");
      setNewDesc("");
      setNewTargetId("");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create suite");
    }
  }

  async function runSuite(suiteId: string) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    setRunning(suiteId);
    try {
      await api.evals.runSuite(suiteId, undefined, data.session.access_token);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run suite");
    } finally {
      setRunning(null);
    }
  }

  async function deleteSuite(suiteId: string) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      await api.evals.deleteSuite(suiteId, data.session.access_token);
      setSuites(suites.filter((s) => s.id !== suiteId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete");
    }
  }

  const targetOptions = newTargetType === "agent" ? agents : blueprints;

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Evals</h1>
          <p className="mt-1 text-muted-foreground">
            Test and evaluate your agents with structured test suites
          </p>
        </div>
        <Button onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? "Cancel" : "New Suite"}
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
            <CardTitle>Create Eval Suite</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Input placeholder="Suite name" value={newName} onChange={(e) => setNewName(e.target.value)} />
            <Input placeholder="Description" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} />
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="text-sm font-medium">Target Type</label>
                <select
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  value={newTargetType}
                  onChange={(e) => { setNewTargetType(e.target.value as typeof newTargetType); setNewTargetId(""); }}
                >
                  <option value="agent">Agent</option>
                  <option value="blueprint">Blueprint</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium">Target</label>
                <select
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  value={newTargetId}
                  onChange={(e) => setNewTargetId(e.target.value)}
                >
                  <option value="">Select...</option>
                  {targetOptions.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </div>
            </div>
            <Button onClick={createSuite} disabled={!newName.trim() || !newTargetId}>
              Create Suite
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="mt-6 space-y-4">
        {loading ? (
          <div className="space-y-3">
            {[1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-lg bg-muted" />)}
          </div>
        ) : suites.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No eval suites yet. Create one to start testing your agents.
          </p>
        ) : (
          suites.map((suite) => {
            const suiteRuns = runs[suite.id] || [];
            const lastRun = suiteRuns[0];
            return (
              <Card key={suite.id}>
                <CardContent className="py-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold">{suite.name}</h3>
                      <p className="text-sm text-muted-foreground">{suite.description}</p>
                      <div className="mt-1 flex items-center gap-2">
                        <Badge variant="outline">{suite.target_type}</Badge>
                        <span className="text-xs text-muted-foreground font-mono">
                          {suite.target_id.slice(0, 8)}
                        </span>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="default"
                        size="sm"
                        onClick={() => runSuite(suite.id)}
                        disabled={running === suite.id}
                      >
                        {running === suite.id ? "Running..." : "Run"}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive"
                        onClick={() => deleteSuite(suite.id)}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                  {lastRun && (
                    <div className="mt-3 flex items-center gap-4 text-sm">
                      <span>
                        Last run: <Badge variant={lastRun.status === "completed" ? "default" : "secondary"}>{lastRun.status}</Badge>
                      </span>
                      {lastRun.pass_rate !== null && (
                        <span className={lastRun.pass_rate >= 0.8 ? "text-green-600" : lastRun.pass_rate >= 0.5 ? "text-yellow-600" : "text-red-600"}>
                          Pass rate: {(lastRun.pass_rate * 100).toFixed(0)}%
                        </span>
                      )}
                      {lastRun.avg_score !== null && (
                        <span className="text-muted-foreground">
                          Avg score: {lastRun.avg_score.toFixed(2)}
                        </span>
                      )}
                      <span className="text-muted-foreground">
                        {lastRun.passed_cases}/{lastRun.total_cases} passed
                      </span>
                    </div>
                  )}
                  {suiteRuns.length > 1 && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {suiteRuns.length} total runs
                    </p>
                  )}
                </CardContent>
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
}
