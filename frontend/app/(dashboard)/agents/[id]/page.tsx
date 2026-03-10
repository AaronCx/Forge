"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import { api, Agent } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { RunnerPanel } from "@/components/runner/RunnerPanel";

export default function AgentDetailPage() {
  const params = useParams();
  const router = useRouter();
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

  async function handleDelete() {
    if (!agent) return;
    if (!confirm("Are you sure you want to delete this agent?")) return;

    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      await api.agents.delete(agent.id, data.session.access_token);
      router.push("/dashboard/agents");
    } catch {
      // handle error
    }
  }

  if (loading) return <p className="text-muted-foreground">Loading agent...</p>;
  if (!agent) return <p className="text-destructive">Agent not found</p>;

  return (
    <div>
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold">{agent.name}</h1>
          <p className="mt-1 text-muted-foreground">{agent.description}</p>
        </div>
        <div className="flex gap-2">
          <Link href={`/dashboard/agents/${agent.id}/edit`}>
            <Button variant="outline">Edit</Button>
          </Link>
          <Button variant="destructive" onClick={handleDelete}>
            Delete
          </Button>
        </div>
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        {agent.tools.map((tool) => (
          <Badge key={tool} variant="outline">
            {tool.replace("_", " ")}
          </Badge>
        ))}
      </div>

      {agent.workflow_steps.length > 0 && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-base">Workflow Steps</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="list-inside list-decimal space-y-1 text-sm">
              {agent.workflow_steps.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}

      <Separator className="my-8" />

      <h2 className="text-xl font-semibold">Run Agent</h2>
      <div className="mt-4">
        <RunnerPanel agent={agent} />
      </div>
    </div>
  );
}
