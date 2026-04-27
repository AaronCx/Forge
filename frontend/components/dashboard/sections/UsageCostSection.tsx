"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  isDemoMode,
  DEMO_COST_SUMMARY,
  DEMO_COST_PROJECTION,
  DEMO_COST_BY_AGENT,
  DEMO_COST_BY_MODEL,
  DEMO_COST_BY_PROVIDER,
  DEMO_COST_WEEK,
  DEMO_COST_MONTH,
} from "@/lib/demo-data";
import { API_URL } from "@/lib/constants";

interface CostSummary {
  period: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost: number;
  request_count: number;
}

interface BreakdownEntry {
  name: string;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  requests: number;
}

interface Projection {
  daily_average: number;
  weekly_total: number;
  monthly_projection: number;
  tokens_per_day: number;
}

function BreakdownTable({ title, rows }: { title: string; rows: BreakdownEntry[] }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No usage data yet.</p>
        ) : (
          <div className="space-y-2">
            {rows.map((entry) => (
              <div
                key={entry.name}
                className="flex items-center justify-between rounded-md border border-border p-3"
                data-seeded="true"
              >
                <div>
                  <Badge variant="outline" className="mb-1">
                    {entry.name}
                  </Badge>
                  <p className="text-xs text-muted-foreground">
                    {entry.requests} requests /{" "}
                    {(entry.input_tokens + entry.output_tokens).toLocaleString()} tokens
                  </p>
                </div>
                <span className="font-mono text-sm font-semibold">
                  ${entry.cost.toFixed(4)}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function UsageCostSection() {
  const [today, setToday] = useState<CostSummary | null>(null);
  const [week, setWeek] = useState<CostSummary | null>(null);
  const [month, setMonth] = useState<CostSummary | null>(null);
  const [byAgent, setByAgent] = useState<BreakdownEntry[]>([]);
  const [byModel, setByModel] = useState<BreakdownEntry[]>([]);
  const [byProvider, setByProvider] = useState<BreakdownEntry[]>([]);
  const [projection, setProjection] = useState<Projection | null>(null);

  useEffect(() => {
    if (isDemoMode()) {
      setToday(DEMO_COST_SUMMARY as CostSummary);
      setWeek(DEMO_COST_WEEK as CostSummary);
      setMonth(DEMO_COST_MONTH as CostSummary);
      setByAgent(DEMO_COST_BY_AGENT);
      setByModel(DEMO_COST_BY_MODEL);
      setByProvider(DEMO_COST_BY_PROVIDER);
      setProjection(DEMO_COST_PROJECTION as Projection);
      return;
    }
    async function load() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) return;
      const token = data.session.access_token;
      try {
        const res = await fetch(`${API_URL}/api/costs/all`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const d = await res.json();
          setToday(d.today);
          setWeek(d.week);
          setMonth(d.month);
          setByAgent(d.by_agent ?? []);
          setByModel(d.by_model ?? []);
          setByProvider(d.by_provider ?? []);
          setProjection(d.projection);
        }
      } catch {
        // API may not be available
      }
    }
    load();
  }, []);

  return (
    <section id="usage" className="scroll-mt-20 space-y-6">
      <h2 className="text-xl font-semibold">Usage &amp; cost</h2>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {[
          { label: "Today", data: today },
          { label: "This Week", data: week },
          { label: "This Month", data: month },
        ].map(({ label, data }) => (
          <Card key={label}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {label}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">
                ${data?.total_cost.toFixed(4) || "0.0000"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {data?.total_tokens.toLocaleString() || 0} tokens
                {" / "}
                {data?.request_count || 0} requests
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {projection && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Monthly Projection</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-8">
              <div>
                <p className="text-2xl font-bold">${projection.monthly_projection.toFixed(2)}</p>
                <p className="text-xs text-muted-foreground">Projected monthly cost</p>
              </div>
              <div>
                <p className="text-lg font-semibold">${projection.daily_average.toFixed(4)}</p>
                <p className="text-xs text-muted-foreground">Daily average</p>
              </div>
              <div>
                <p className="text-lg font-semibold">
                  {projection.tokens_per_day.toLocaleString()}
                </p>
                <p className="text-xs text-muted-foreground">Tokens/day</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {today && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Token Breakdown (Today)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm">Input Tokens</span>
                <span className="font-mono text-sm">
                  {today.total_input_tokens.toLocaleString()}
                </span>
              </div>
              <div className="h-3 w-full rounded-full bg-muted">
                <div
                  className="h-3 rounded-full bg-blue-500"
                  style={{
                    width: `${
                      today.total_tokens > 0
                        ? (today.total_input_tokens / today.total_tokens) * 100
                        : 0
                    }%`,
                  }}
                />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">Output Tokens</span>
                <span className="font-mono text-sm">
                  {today.total_output_tokens.toLocaleString()}
                </span>
              </div>
              <div className="h-3 w-full rounded-full bg-muted">
                <div
                  className="h-3 rounded-full bg-green-500"
                  style={{
                    width: `${
                      today.total_tokens > 0
                        ? (today.total_output_tokens / today.total_tokens) * 100
                        : 0
                    }%`,
                  }}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <BreakdownTable title="Cost by Agent" rows={byAgent} />
      <BreakdownTable title="Cost by Provider" rows={byProvider} />
      <BreakdownTable title="Cost by Model" rows={byModel} />
    </section>
  );
}
