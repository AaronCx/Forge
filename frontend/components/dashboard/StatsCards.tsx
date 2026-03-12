"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface StatsCardsProps {
  stats: {
    total_agents: number;
    total_runs: number;
    total_tokens: number;
    runs_this_hour: number;
  };
  loading: boolean;
}

export function StatsCards({ stats, loading }: StatsCardsProps) {
  const cards = [
    { title: "Total Agents", value: stats.total_agents },
    { title: "Total Runs", value: stats.total_runs },
    { title: "Tokens Used", value: stats.total_tokens.toLocaleString() },
    { title: "Runs This Hour", value: `${stats.runs_this_hour}/10` },
  ];

  return (
    <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.title}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {card.title}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="h-8 w-20 animate-pulse rounded bg-muted" />
            ) : (
              <p className="text-2xl font-bold">{card.value}</p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
