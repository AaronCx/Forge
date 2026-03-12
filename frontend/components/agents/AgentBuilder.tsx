"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { api, AgentCreate } from "@/lib/api";
import { isDemoMode } from "@/lib/demo-data";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ModelSelector } from "@/components/ModelSelector";
import { ToolSelector } from "./ToolSelector";
import { WorkflowEditor } from "./WorkflowEditor";

interface AgentBuilderProps {
  initialData?: Partial<AgentCreate> & { id?: string };
  mode: "create" | "edit";
}

export function AgentBuilder({ initialData, mode }: AgentBuilderProps) {
  const router = useRouter();
  const [name, setName] = useState(initialData?.name || "");
  const [description, setDescription] = useState(initialData?.description || "");
  const [systemPrompt, setSystemPrompt] = useState(initialData?.system_prompt || "");
  const [tools, setTools] = useState<string[]>(initialData?.tools || []);
  const [workflowSteps, setWorkflowSteps] = useState<string[]>(initialData?.workflow_steps || []);
  const [model, setModel] = useState<string | null>(initialData?.model || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");

    if (isDemoMode()) {
      setError("Saving agents is disabled in demo mode");
      setLoading(false);
      return;
    }

    const { data } = await supabase.auth.getSession();
    if (!data.session) {
      setError("Not authenticated");
      setLoading(false);
      return;
    }

    const agentData: AgentCreate = {
      name,
      description,
      system_prompt: systemPrompt,
      tools,
      workflow_steps: workflowSteps.filter((s) => s.trim()),
      model,
    };

    try {
      if (mode === "edit" && initialData?.id) {
        await api.agents.update(initialData.id, agentData, data.session.access_token);
      } else {
        await api.agents.create(agentData, data.session.access_token);
      }
      router.push("/dashboard/agents");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save agent");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Agent Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Document Analyzer"
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Input
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What does this agent do?"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="systemPrompt">System Prompt</Label>
            <Textarea
              id="systemPrompt"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="You are a helpful assistant that..."
              rows={6}
              required
            />
          </div>
          <ModelSelector value={model} onChange={setModel} />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <ToolSelector selected={tools} onChange={setTools} />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <WorkflowEditor steps={workflowSteps} onChange={setWorkflowSteps} />
        </CardContent>
      </Card>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex gap-3">
        <Button type="submit" disabled={loading}>
          {loading
            ? "Saving..."
            : mode === "edit"
              ? "Update Agent"
              : "Create Agent"}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => router.back()}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
