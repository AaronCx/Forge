"use client";

import Link from "next/link";
import { Agent } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { isDemoMode } from "@/lib/demo-data";

interface AgentCardProps {
  agent: Agent;
}

export function AgentCard({ agent }: AgentCardProps) {
  const demoSuffix = isDemoMode() ? "?demo=true" : "";

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="truncate text-lg" title={agent.name}>
            {agent.name}
          </CardTitle>
          {agent.is_template && <Badge variant="secondary">Template</Badge>}
        </div>
        <p className="line-clamp-2 text-sm text-muted-foreground">
          {agent.description}
        </p>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-1.5">
          {agent.tools.map((tool) => (
            <Badge key={tool} variant="outline" className="text-xs">
              {tool.replaceAll("_", " ")}
            </Badge>
          ))}
        </div>
        <div className="mt-4 flex gap-2">
          <Link href={`/dashboard/agents/${agent.id}${demoSuffix}`}>
            <Button size="sm">Run</Button>
          </Link>
          <Link href={`/dashboard/agents/${agent.id}/edit${demoSuffix}`}>
            <Button size="sm" variant="outline">
              Edit
            </Button>
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
