"use client";

import { useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";
import { MetricsBar } from "@/components/dashboard/MetricsBar";
import { AgentStatusGrid, AgentHeartbeat } from "@/components/dashboard/AgentStatusGrid";
import { EventTimeline, TimelineEvent } from "@/components/dashboard/EventTimeline";
import { isDemoMode, DEMO_METRICS, DEMO_ACTIVE_AGENTS, DEMO_TIMELINE } from "@/lib/demo-data";
import { API_URL } from "@/lib/constants";

interface Props {
  onConnectedChange?: (connected: boolean) => void;
}

export function LiveStatusSection({ onConnectedChange }: Props) {
  const [metrics, setMetrics] = useState({
    active_runs: 0,
    total_agents: 0,
    tokens_today: 0,
    cost_today: 0,
  });
  const [activeAgents, setActiveAgents] = useState<AgentHeartbeat[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef = useRef(0);

  useEffect(() => {
    let cancelled = false;

    if (isDemoMode()) {
      setMetrics(DEMO_METRICS);
      setActiveAgents(DEMO_ACTIVE_AGENTS as AgentHeartbeat[]);
      setTimeline(DEMO_TIMELINE as TimelineEvent[]);
      setLoading(false);
      onConnectedChange?.(true);
      return;
    }

    async function connect() {
      const { data } = await supabase.auth.getSession();
      if (!data.session || cancelled) return;
      const token = data.session.access_token;

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
        // API may be unavailable; keep prior state
      } finally {
        setLoading(false);
      }

      const es = new EventSource(
        `${API_URL}/api/dashboard/stream?token=${encodeURIComponent(token)}`
      );

      es.onopen = () => {
        onConnectedChange?.(true);
        retryCountRef.current = 0;
      };

      es.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.metrics) setMetrics(payload.metrics);
          if (payload.active_agents) setActiveAgents(payload.active_agents);
        } catch {
          // ignore malformed SSE frames
        }
      };

      es.onerror = () => {
        onConnectedChange?.(false);
        es.close();
        if (!cancelled) {
          const delay = Math.min(5000 * 2 ** retryCountRef.current, 30000);
          retryCountRef.current++;
          reconnectTimerRef.current = setTimeout(connect, delay);
        }
      };

      eventSourceRef.current = es;
    }

    connect();

    return () => {
      cancelled = true;
      eventSourceRef.current?.close();
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    };
  }, [onConnectedChange]);

  return (
    <section id="live" className="scroll-mt-20 space-y-6">
      <h2 className="text-xl font-semibold">Live status</h2>
      <MetricsBar metrics={metrics} loading={loading} />
      <div>
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">Active Agents</h3>
        <AgentStatusGrid agents={activeAgents} />
      </div>
      <EventTimeline events={timeline} />
    </section>
  );
}
