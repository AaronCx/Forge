"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface DashboardMetrics {
  active_runs: number;
  total_agents: number;
  tokens_today: number;
  cost_today: number;
}

interface MetricsBarProps {
  metrics: DashboardMetrics;
  loading: boolean;
}

export function MetricsBar({ metrics, loading }: MetricsBarProps) {
  const cards = [
    {
      title: "Active Runs",
      value: metrics.active_runs,
      color: metrics.active_runs > 0 ? "text-green-500" : "",
    },
    {
      title: "Total Agents",
      value: metrics.total_agents,
      color: "",
    },
    {
      title: "Tokens Today",
      value: metrics.tokens_today.toLocaleString(),
      color: "",
    },
    {
      title: "Cost Today",
      value: `$${metrics.cost_today.toFixed(4)}`,
      color: "",
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.title}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {card.title}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className={`text-2xl font-bold ${card.color}`}>
              {loading ? "..." : card.value}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
