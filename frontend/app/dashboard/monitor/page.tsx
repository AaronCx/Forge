"use client";

import { useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";
import { MetricsBar } from "@/components/dashboard/MetricsBar";
import { AgentStatusGrid, AgentHeartbeat } from "@/components/dashboard/AgentStatusGrid";
import { EventTimeline, TimelineEvent } from "@/components/dashboard/EventTimeline";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function MonitorPage() {
  const [metrics, setMetrics] = useState({
    active_runs: 0,
    total_agents: 0,
    tokens_today: 0,
    cost_today: 0,
  });
  const [activeAgents, setActiveAgents] = useState<AgentHeartbeat[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function connect() {
      const { data } = await supabase.auth.getSession();
      if (!data.session || cancelled) return;

      const token = data.session.access_token;

      // Initial data fetch
      try {
        const [metricsRes, activeRes, timelineRes] = await Promise.all([
          fetch(`${API_URL}/api/dashboard/metrics`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${API_URL}/api/dashboard/active`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${API_URL}/api/dashboard/timeline`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        ]);

        if (metricsRes.ok) setMetrics(await metricsRes.json());
        if (activeRes.ok) setActiveAgents(await activeRes.json());
        if (timelineRes.ok) setTimeline(await timelineRes.json());
      } catch {
        // API might not be available
      } finally {
        setLoading(false);
      }

      // Connect SSE stream
      const es = new EventSource(
        `${API_URL}/api/dashboard/stream?token=${encodeURIComponent(token)}`
      );

      es.onopen = () => setConnected(true);

      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.metrics) setMetrics(data.metrics);
          if (data.active_agents) setActiveAgents(data.active_agents);
        } catch {
          // Ignore parse errors
        }
      };

      es.onerror = () => {
        setConnected(false);
        es.close();
        // Reconnect after 5s
        if (!cancelled) {
          setTimeout(connect, 5000);
        }
      };

      eventSourceRef.current = es;
    }

    connect();

    return () => {
      cancelled = true;
      eventSourceRef.current?.close();
    };
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Live Monitor</h1>
          <p className="mt-1 text-muted-foreground">
            Real-time agent execution dashboard
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="relative flex h-3 w-3">
            <span
              className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${
                connected ? "animate-ping bg-green-500" : "bg-red-500"
              }`}
            />
            <span
              className={`relative inline-flex h-3 w-3 rounded-full ${
                connected ? "bg-green-500" : "bg-red-500"
              }`}
            />
          </span>
          <span className="text-sm text-muted-foreground">
            {connected ? "Connected" : "Disconnected"}
          </span>
        </div>
      </div>

      <MetricsBar metrics={metrics} loading={loading} />

      <div>
        <h2 className="mb-3 text-xl font-semibold">Active Agents</h2>
        <AgentStatusGrid agents={activeAgents} />
      </div>

      <EventTimeline events={timeline} />
    </div>
  );
}
