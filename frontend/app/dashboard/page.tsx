"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import { api, Blueprint } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { StatsCards } from "@/components/dashboard/StatsCards";
import { RunHistory } from "@/components/dashboard/RunHistory";
import { isDemoMode, DEMO_STATS } from "@/lib/demo-data";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function DashboardPage() {
  const [stats, setStats] = useState({
    total_agents: 0,
    total_runs: 0,
    total_tokens: 0,
    runs_this_hour: 0,
  });
  const [blueprints, setBlueprints] = useState<Blueprint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isDemoMode()) {
      setStats(DEMO_STATS);
      setLoading(false);
      return;
    }

    async function loadStats() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) return;

      try {
        const [s, bps] = await Promise.all([
          api.stats.get(data.session.access_token),
          api.blueprints.list(data.session.access_token).catch(() => []),
        ]);
        setStats(s);
        setBlueprints(bps);
      } catch {
        setError("Failed to load dashboard data. Check your connection.");
      } finally {
        setLoading(false);
      }
    }
    loadStats();
  }, []);

  return (
    <div>
      {error && (
        <div className="mb-4 rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}
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

      {blueprints.length > 0 && (
        <div className="mt-8">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">Recent Blueprints</h2>
            <Link href="/dashboard/blueprints">
              <Button variant="ghost" size="sm">View all</Button>
            </Link>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {blueprints.slice(0, 3).map((bp) => (
              <Link key={bp.id} href={`/dashboard/blueprints/${bp.id}/edit`}>
                <Card className="h-full transition-colors hover:border-primary/50">
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between">
                      <CardTitle className="text-sm">{bp.name}</CardTitle>
                      <Badge variant="outline" className="text-[10px]">
                        {bp.nodes.length} nodes
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-muted-foreground line-clamp-2">
                      {bp.description}
                    </p>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="mt-8">
        <h2 className="text-xl font-semibold">Recent Runs</h2>
        <RunHistory />
      </div>
    </div>
  );
}
