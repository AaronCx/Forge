"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export interface TimelineEvent {
  id: string;
  agent_id: string;
  agent_name: string;
  run_id: string | null;
  state: string;
  severity: "info" | "warning" | "error" | "success";
  current_step: number;
  total_steps: number;
  tokens_used: number;
  cost_estimate: number;
  output_preview: string;
  updated_at: string;
}

interface EventTimelineProps {
  events: TimelineEvent[];
}

const severityColors: Record<string, string> = {
  info: "bg-blue-500",
  warning: "bg-yellow-500",
  error: "bg-red-500",
  success: "bg-green-500",
};

const severityBadge: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  info: "secondary",
  warning: "secondary",
  error: "destructive",
  success: "default",
};

export function EventTimeline({ events }: EventTimelineProps) {
  const [filter, setFilter] = useState<string | null>(null);

  const filtered = filter
    ? events.filter((e) => e.agent_name === filter)
    : events;

  const uniqueAgents = [...new Set(events.map((e) => e.agent_name))];

  function formatTime(iso: string) {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function stateMessage(event: TimelineEvent): string {
    switch (event.state) {
      case "starting":
        return "Agent starting...";
      case "running":
        return `Running step ${event.current_step}/${event.total_steps}`;
      case "stalled":
        return "Agent stalled — no updates for 30s";
      case "completed":
        return `Completed (${event.tokens_used.toLocaleString()} tokens, $${event.cost_estimate.toFixed(4)})`;
      case "failed":
        return "Agent failed";
      default:
        return event.state;
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">Event Timeline</h3>
        <div className="flex gap-1">
          <Button
            variant={filter === null ? "default" : "outline"}
            size="sm"
            className="h-7 text-xs"
            onClick={() => setFilter(null)}
          >
            All
          </Button>
          {uniqueAgents.map((name) => (
            <Button
              key={name}
              variant={filter === name ? "default" : "outline"}
              size="sm"
              className="h-7 text-xs"
              onClick={() => setFilter(name)}
            >
              {name}
            </Button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">No events yet.</p>
      ) : (
        <div className="max-h-80 space-y-1 overflow-y-auto">
          {filtered.map((event) => (
            <div
              key={event.id}
              className="flex items-start gap-3 rounded-md border border-border p-2.5"
            >
              <div
                className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${severityColors[event.severity]}`}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{event.agent_name}</span>
                  <Badge variant={severityBadge[event.severity]} className="text-[10px]">
                    {event.state}
                  </Badge>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {formatTime(event.updated_at)}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  {stateMessage(event)}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
