"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import { api, Agent } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { AgentCard } from "@/components/agents/AgentCard";

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [templates, setTemplates] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) return;

      try {
        const [userAgents, templateAgents] = await Promise.all([
          api.agents.list(data.session.access_token),
          api.agents.templates(data.session.access_token),
        ]);
        setAgents(userAgents);
        setTemplates(templateAgents);
      } catch {
        // API may not be running
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Agents</h1>
          <p className="mt-1 text-muted-foreground">
            Create and manage your AI workflow agents
          </p>
        </div>
        <Link href="/dashboard/agents/new">
          <Button>Create Agent</Button>
        </Link>
      </div>

      {loading ? (
        <p className="mt-8 text-muted-foreground">Loading agents...</p>
      ) : (
        <>
          {agents.length > 0 && (
            <div className="mt-8">
              <h2 className="text-xl font-semibold">Your Agents</h2>
              <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                {agents.map((agent) => (
                  <AgentCard key={agent.id} agent={agent} />
                ))}
              </div>
            </div>
          )}

          {templates.length > 0 && (
            <div className="mt-8">
              <h2 className="text-xl font-semibold">Templates</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Pre-built agents ready to use
              </p>
              <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                {templates.map((agent) => (
                  <AgentCard key={agent.id} agent={agent} />
                ))}
              </div>
            </div>
          )}

          {agents.length === 0 && templates.length === 0 && (
            <div className="mt-8 rounded-lg border border-dashed border-border p-12 text-center">
              <h3 className="text-lg font-semibold">No agents yet</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Create your first agent to get started.
              </p>
              <Link href="/dashboard/agents/new">
                <Button className="mt-4">Create Agent</Button>
              </Link>
            </div>
          )}
        </>
      )}
    </div>
  );
}
