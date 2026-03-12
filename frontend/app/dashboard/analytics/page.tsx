"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { isDemoMode, DEMO_COST_SUMMARY, DEMO_COST_PROJECTION } from "@/lib/demo-data";
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

export default function AnalyticsPage() {
  const [today, setToday] = useState<CostSummary | null>(null);
  const [week, setWeek] = useState<CostSummary | null>(null);
  const [month, setMonth] = useState<CostSummary | null>(null);
  const [byAgent, setByAgent] = useState<BreakdownEntry[]>([]);
  const [byModel, setByModel] = useState<BreakdownEntry[]>([]);
  const [projection, setProjection] = useState<Projection | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isDemoMode()) {
      setToday(DEMO_COST_SUMMARY as CostSummary);
      setWeek({ ...DEMO_COST_SUMMARY, period: "week", total_tokens: 156_000, total_cost: 0.196, request_count: 312 } as CostSummary);
      setMonth({ ...DEMO_COST_SUMMARY, period: "month", total_tokens: 482_350, total_cost: 0.84, request_count: 1247 } as CostSummary);
      setByAgent([
        { name: "Research Agent", input_tokens: 8200, output_tokens: 3100, cost: 0.012, requests: 18 },
        { name: "Data Extractor", input_tokens: 5400, output_tokens: 1800, cost: 0.008, requests: 14 },
        { name: "Code Reviewer", input_tokens: 4600, output_tokens: 1400, cost: 0.007, requests: 15 },
      ]);
      setByModel([
        { name: "gpt-4o-mini", input_tokens: 18200, output_tokens: 6300, cost: 0.031, requests: 47 },
      ]);
      setProjection(DEMO_COST_PROJECTION as Projection);
      setLoading(false);
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
          setByAgent(d.by_agent);
          setByModel(d.by_model);
          setProjection(d.projection);
        }
      } catch {
        // API may not be available
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div>
        <h1 className="text-3xl font-bold">Analytics</h1>
        <p className="mt-4 text-muted-foreground">Loading cost data...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Analytics</h1>
        <p className="mt-1 text-muted-foreground">
          Token usage and cost tracking
        </p>
      </div>

      {/* Summary cards */}
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

      {/* Projection */}
      {projection && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Monthly Projection</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-8">
              <div>
                <p className="text-2xl font-bold">${projection.monthly_projection.toFixed(2)}</p>
                <p className="text-xs text-muted-foreground">Projected monthly cost</p>
              </div>
              <div>
                <p className="text-lg font-semibold">${projection.daily_average.toFixed(4)}</p>
                <p className="text-xs text-muted-foreground">Daily average</p>
              </div>
              <div>
                <p className="text-lg font-semibold">{projection.tokens_per_day.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Tokens/day</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Token breakdown by input/output */}
      {today && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Token Breakdown (Today)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm">Input Tokens</span>
                <span className="font-mono text-sm">{today.total_input_tokens.toLocaleString()}</span>
              </div>
              <div className="h-3 w-full rounded-full bg-muted">
                <div
                  className="h-3 rounded-full bg-blue-500"
                  style={{
                    width: `${today.total_tokens > 0 ? (today.total_input_tokens / today.total_tokens) * 100 : 0}%`,
                  }}
                />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">Output Tokens</span>
                <span className="font-mono text-sm">{today.total_output_tokens.toLocaleString()}</span>
              </div>
              <div className="h-3 w-full rounded-full bg-muted">
                <div
                  className="h-3 rounded-full bg-green-500"
                  style={{
                    width: `${today.total_tokens > 0 ? (today.total_output_tokens / today.total_tokens) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* By Agent */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Cost by Agent</CardTitle>
        </CardHeader>
        <CardContent>
          {byAgent.length === 0 ? (
            <p className="text-sm text-muted-foreground">No usage data yet.</p>
          ) : (
            <div className="space-y-2">
              {byAgent.map((entry) => (
                <div
                  key={entry.name}
                  className="flex items-center justify-between rounded-md border border-border p-3"
                >
                  <div>
                    <p className="text-sm font-medium">{entry.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {entry.requests} requests / {(entry.input_tokens + entry.output_tokens).toLocaleString()} tokens
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

      {/* By Model */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Cost by Model</CardTitle>
        </CardHeader>
        <CardContent>
          {byModel.length === 0 ? (
            <p className="text-sm text-muted-foreground">No usage data yet.</p>
          ) : (
            <div className="flex flex-wrap gap-3">
              {byModel.map((entry) => (
                <div key={entry.name} className="rounded-lg border border-border p-3">
                  <Badge variant="outline" className="mb-1">
                    {entry.name}
                  </Badge>
                  <p className="font-mono text-lg font-bold">${entry.cost.toFixed(4)}</p>
                  <p className="text-xs text-muted-foreground">
                    {entry.requests} requests
                  </p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
