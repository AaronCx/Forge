"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { api, Agent, PromptVersion } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { isDemoMode } from "@/lib/demo-data";

export default function PromptsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string>("");
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<PromptVersion | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isDemoMode()) {
      setAgents([]);
      setLoading(false);
      return;
    }
    loadAgents();
  }, []);

  useEffect(() => {
    if (selectedAgent) {
      loadVersions(selectedAgent);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAgent]);

  async function loadAgents() {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;
    try {
      const list = await api.agents.list(data.session.access_token);
      setAgents(list);
      if (list.length > 0) {
        setSelectedAgent(list[0].id);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  async function loadVersions(agentId: string) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;
    try {
      const list = await api.promptVersions.list(agentId, data.session.access_token);
      setVersions(list);
    } catch {
      setVersions([]);
    }
  }

  async function loadVersionDetail(versionId: string) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;
    try {
      const detail = await api.promptVersions.get(versionId, data.session.access_token);
      setSelectedVersion(detail);
    } catch {
      // ignore
    }
  }

  async function handleRollback(versionId: string) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;
    try {
      await api.promptVersions.rollback(versionId, data.session.access_token);
      await loadVersions(selectedAgent);
      setSelectedVersion(null);
    } catch {
      // ignore
    }
  }

  async function handleCreateVersion() {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    // Get current agent prompt
    const agent = agents.find((a) => a.id === selectedAgent);
    if (!agent) return;

    try {
      await api.promptVersions.create(
        selectedAgent,
        { system_prompt: agent.system_prompt, change_summary: "Manual snapshot" },
        data.session.access_token,
      );
      await loadVersions(selectedAgent);
    } catch {
      // ignore
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Prompt Versions</h1>
          <p className="mt-1 text-muted-foreground">
            Track, compare, and rollback system prompt changes
          </p>
        </div>
        {selectedAgent && (
          <Button size="sm" onClick={handleCreateVersion}>
            Snapshot Current
          </Button>
        )}
      </div>

      {/* Agent selector */}
      <div className="mt-6 flex gap-2 flex-wrap">
        {agents.map((agent) => (
          <Button
            key={agent.id}
            variant={selectedAgent === agent.id ? "default" : "outline"}
            size="sm"
            onClick={() => {
              setSelectedAgent(agent.id);
              setSelectedVersion(null);
            }}
          >
            {agent.name}
          </Button>
        ))}
      </div>

      {loading ? (
        <div className="mt-6 space-y-2">
          {[1, 2].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : versions.length === 0 ? (
        <p className="mt-6 text-sm text-muted-foreground">
          {selectedAgent
            ? "No prompt versions yet. Click \"Snapshot Current\" to save the current prompt, or versions are auto-created when you edit a prompt."
            : "Select an agent to view prompt versions."}
        </p>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Version list */}
          <div className="space-y-2">
            {versions.map((version) => (
              <Card
                key={version.id}
                className={`cursor-pointer transition-colors hover:border-primary/50 ${
                  selectedVersion?.id === version.id ? "border-primary" : ""
                }`}
                onClick={() => loadVersionDetail(version.id)}
              >
                <CardContent className="flex items-center gap-3 py-3">
                  <span className="font-mono text-sm font-bold">
                    v{version.version_number}
                  </span>
                  {version.is_active && (
                    <Badge className="bg-green-500 text-white">active</Badge>
                  )}
                  <span className="flex-1 truncate text-sm text-muted-foreground">
                    {version.change_summary}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {new Date(version.created_at).toLocaleDateString()}
                  </span>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Version detail */}
          {selectedVersion && (
            <div className="space-y-4">
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-bold">
                      Version {selectedVersion.version_number}
                    </h3>
                    {!selectedVersion.is_active && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleRollback(selectedVersion.id)}
                      >
                        Rollback to this version
                      </Button>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground mb-3">
                    {selectedVersion.change_summary}
                  </p>

                  {selectedVersion.system_prompt && (
                    <div>
                      <p className="text-xs font-medium text-muted-foreground mb-1">
                        System Prompt
                      </p>
                      <pre className="rounded bg-muted p-3 text-xs overflow-auto max-h-64 whitespace-pre-wrap">
                        {selectedVersion.system_prompt}
                      </pre>
                    </div>
                  )}

                  {selectedVersion.diff_from_previous && (
                    <div className="mt-3">
                      <p className="text-xs font-medium text-muted-foreground mb-1">
                        Diff from previous
                      </p>
                      <pre className="rounded bg-muted p-3 text-xs overflow-auto max-h-48 font-mono">
                        {selectedVersion.diff_from_previous.split("\n").map((line, i) => {
                          let color = "";
                          if (line.startsWith("+")) color = "text-green-500";
                          else if (line.startsWith("-")) color = "text-red-500";
                          else if (line.startsWith("@@")) color = "text-blue-500";
                          return (
                            <span key={i} className={color}>
                              {line}
                              {"\n"}
                            </span>
                          );
                        })}
                      </pre>
                    </div>
                  )}

                  <p className="mt-3 text-xs text-muted-foreground">
                    Created: {new Date(selectedVersion.created_at).toLocaleString()}
                  </p>
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
