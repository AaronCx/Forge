"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface AgentHeartbeat {
  id: string;
  agent_id: string;
  run_id: string | null;
  state: string;
  current_step: number;
  total_steps: number;
  tokens_used: number;
  cost_estimate: number;
  output_preview: string;
  updated_at: string;
  agents?: { name: string; description: string; tools: string[] };
}

interface AgentStatusGridProps {
  agents: AgentHeartbeat[];
}

const stateColors: Record<string, string> = {
  starting: "bg-yellow-500",
  running: "bg-green-500",
  stalled: "bg-orange-500",
  completed: "bg-blue-500",
  failed: "bg-red-500",
  idle: "bg-gray-500",
};

const stateBadgeVariant: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  starting: "secondary",
  running: "default",
  stalled: "destructive",
  completed: "outline",
  failed: "destructive",
  idle: "secondary",
};

export function AgentStatusGrid({ agents }: AgentStatusGridProps) {
  if (agents.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-8 text-center">
        <p className="text-sm text-muted-foreground">
          No active agents. Run an agent to see live status here.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {agents.map((agent) => {
        const name = agent.agents?.name || "Unknown Agent";
        const progress =
          agent.total_steps > 0
            ? Math.round((agent.current_step / agent.total_steps) * 100)
            : 0;
        const isActive = agent.state === "running" || agent.state === "starting";

        return (
          <Card key={agent.id} className="relative overflow-hidden">
            {isActive && (
              <div className="absolute right-3 top-3">
                <span className="relative flex h-3 w-3">
                  <span
                    className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${stateColors[agent.state]}`}
                  />
                  <span
                    className={`relative inline-flex h-3 w-3 rounded-full ${stateColors[agent.state]}`}
                  />
                </span>
              </div>
            )}
            <CardHeader className="pb-2">
              <div className="flex items-center gap-2">
                <CardTitle className="text-base">{name}</CardTitle>
                <Badge variant={stateBadgeVariant[agent.state] || "secondary"}>
                  {agent.state}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {/* Progress bar */}
              <div>
                <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                  <span>
                    Step {agent.current_step}/{agent.total_steps}
                  </span>
                  <span>{progress}%</span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted">
                  <div
                    className={`h-2 rounded-full transition-all duration-500 ${stateColors[agent.state]}`}
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>

              {/* Token & cost info */}
              <div className="flex gap-4 text-xs text-muted-foreground">
                <span>{agent.tokens_used.toLocaleString()} tokens</span>
                <span>${Number(agent.cost_estimate).toFixed(4)}</span>
              </div>

              {/* Output preview */}
              {agent.output_preview && (
                <p className="line-clamp-2 text-xs text-muted-foreground">
                  {agent.output_preview}
                </p>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
