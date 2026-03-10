"use client";

import { AgentBuilder } from "@/components/agents/AgentBuilder";

export default function NewAgentPage() {
  return (
    <div>
      <h1 className="text-3xl font-bold">Create Agent</h1>
      <p className="mt-1 text-muted-foreground">
        Configure a new AI workflow agent
      </p>
      <div className="mt-8">
        <AgentBuilder mode="create" />
      </div>
    </div>
  );
}
