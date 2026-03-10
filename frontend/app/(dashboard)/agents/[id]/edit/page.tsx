"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { api, Agent } from "@/lib/api";
import { AgentBuilder } from "@/components/agents/AgentBuilder";

export default function EditAgentPage() {
  const params = useParams();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) return;

      try {
        const a = await api.agents.get(params.id as string, data.session.access_token);
        setAgent(a);
      } catch {
        // handle error
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [params.id]);

  if (loading) return <p className="text-muted-foreground">Loading agent...</p>;
  if (!agent) return <p className="text-destructive">Agent not found</p>;

  return (
    <div>
      <h1 className="text-3xl font-bold">Edit Agent</h1>
      <p className="mt-1 text-muted-foreground">Update {agent.name}</p>
      <div className="mt-8">
        <AgentBuilder
          mode="edit"
          initialData={{
            id: agent.id,
            name: agent.name,
            description: agent.description,
            system_prompt: agent.system_prompt,
            tools: agent.tools,
            workflow_steps: agent.workflow_steps,
          }}
        />
      </div>
    </div>
  );
}
