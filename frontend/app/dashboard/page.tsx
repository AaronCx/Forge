"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { StatsCards } from "@/components/dashboard/StatsCards";
import { RunHistory } from "@/components/dashboard/RunHistory";

export default function DashboardPage() {
  const [stats, setStats] = useState({
    total_agents: 0,
    total_runs: 0,
    total_tokens: 0,
    runs_this_hour: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadStats() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) return;

      try {
        const s = await api.stats.get(data.session.access_token);
        setStats(s);
      } catch {
        // Stats endpoint may not be available yet
      } finally {
        setLoading(false);
      }
    }
    loadStats();
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Dashboard</h1>
          <p className="mt-1 text-muted-foreground">
            Overview of your agents and usage
          </p>
        </div>
        <Link href="/dashboard/agents/new">
          <Button>Create Agent</Button>
        </Link>
      </div>

      <StatsCards stats={stats} loading={loading} />

      <div className="mt-8">
        <h2 className="text-xl font-semibold">Recent Runs</h2>
        <RunHistory />
      </div>
    </div>
  );
}
