"use client";

import { useEffect, useState } from "react";
import { Cpu } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { isDemoMode, DEMO_PROVIDERS, DEMO_MODEL_CATALOG } from "@/lib/demo-data";
import { supabase } from "@/lib/supabase";
import { API_URL } from "@/lib/constants";

interface ProviderRow {
  provider: string;
  status: "healthy" | "degraded" | "down";
  latency_ms: number;
  default_model: string;
  api_key_masked: string;
}

interface ModelRow {
  provider: string;
  name: string;
  context: number;
  input_cost: number;
  output_cost: number;
  supports_streaming: boolean;
}

function StatusBadge({ status }: { status: ProviderRow["status"] }) {
  const variant: Record<ProviderRow["status"], string> = {
    healthy: "bg-emerald-500/15 text-emerald-300 border-emerald-700",
    degraded: "bg-yellow-500/15 text-yellow-300 border-yellow-700",
    down: "bg-red-500/15 text-red-300 border-red-700",
  };
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${variant[status]}`}>
      {status}
    </span>
  );
}

export default function ProvidersPage() {
  const [providers, setProviders] = useState<ProviderRow[]>([]);
  const [models, setModels] = useState<ModelRow[]>([]);
  const [demo, setDemo] = useState(false);
  const [filter, setFilter] = useState("");
  const [comparePrompt, setComparePrompt] = useState("Summarize the request to refactor scraper.py for clarity.");
  const [selectedModels, setSelectedModels] = useState<string[]>([
    "openai:gpt-4o-mini",
    "anthropic:claude-haiku-4-5",
  ]);

  useEffect(() => {
    if (isDemoMode()) {
      setDemo(true);
      setProviders(DEMO_PROVIDERS);
      setModels(DEMO_MODEL_CATALOG);
      return;
    }
    async function load() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) return;
      const token = data.session.access_token;
      try {
        const [healthRes, modelsRes] = await Promise.all([
          fetch(`${API_URL}/api/providers/health`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_URL}/api/providers/models`, { headers: { Authorization: `Bearer ${token}` } }),
        ]);
        if (healthRes.ok) {
          const healthList = await healthRes.json();
          setProviders(
            healthList.map((h: { provider: string; status: string; latency_ms?: number }) => ({
              provider: h.provider,
              status: (h.status === "healthy" || h.status === "degraded" || h.status === "down" ? h.status : "down") as ProviderRow["status"],
              latency_ms: h.latency_ms ?? 0,
              default_model: "—",
              api_key_masked: "configured",
            }))
          );
        }
        if (modelsRes.ok) {
          const list = (await modelsRes.json()) as Array<{
            provider: string;
            name: string;
            context_window?: number;
            input_cost_per_token?: number;
            output_cost_per_token?: number;
            supports_streaming?: boolean;
          }>;
          setModels(
            list.map((m) => ({
              provider: m.provider,
              name: m.name,
              context: m.context_window ?? 0,
              input_cost: m.input_cost_per_token ?? 0,
              output_cost: m.output_cost_per_token ?? 0,
              supports_streaming: m.supports_streaming ?? false,
            }))
          );
        }
      } catch {
        // backend may be unreachable
      }
    }
    load();
  }, []);

  const filteredModels = models.filter((m) => {
    const q = filter.toLowerCase();
    return !q || m.name.toLowerCase().includes(q) || m.provider.toLowerCase().includes(q);
  });

  function toggleModel(key: string) {
    setSelectedModels((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  }

  function handleTest(provider: string) {
    if (demo) {
      toast("Add your own key to test", {
        description: "Demo provider keys are read-only.",
      });
      return;
    }
    toast.message(`Testing ${provider}...`);
  }

  function handleCompare() {
    if (demo) {
      toast("Compare runs against pre-recorded outputs", {
        description: "Connect a Forge runtime to run live comparisons.",
      });
      return;
    }
    toast.message("Running comparison...");
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3">
        <Cpu className="mt-1 h-6 w-6 text-muted-foreground" aria-hidden="true" />
        <div>
          <h1 className="text-3xl font-bold">Providers</h1>
          <p className="mt-1 text-muted-foreground">
            Multi-model provider registry, health checks, and side-by-side comparison.
          </p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {providers.map((p) => (
          <Card key={p.provider} data-seeded={demo}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-mono">{p.provider}</CardTitle>
                <StatusBadge status={p.status} />
              </div>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <p className="text-muted-foreground">Default · {p.default_model}</p>
              <p className="font-mono text-muted-foreground">{p.api_key_masked}</p>
              <p className="text-muted-foreground">{p.latency_ms || "—"} ms</p>
              <Button size="sm" variant="outline" className="w-full" onClick={() => handleTest(p.provider)}>
                Test
              </Button>
            </CardContent>
          </Card>
        ))}
        {providers.length === 0 && (
          <p className="col-span-full text-sm text-muted-foreground">
            No providers configured. Add an API key in Settings to register one.
          </p>
        )}
      </div>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-sm font-medium">Model catalog</CardTitle>
            <Input
              type="search"
              placeholder="Filter models..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="h-8 w-48 text-xs"
            />
          </div>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="py-2 pr-4 font-medium">Provider</th>
                <th className="py-2 pr-4 font-medium">Model</th>
                <th className="py-2 pr-4 font-medium">Context</th>
                <th className="py-2 pr-4 font-medium">Input $/Mtok</th>
                <th className="py-2 pr-4 font-medium">Output $/Mtok</th>
                <th className="py-2 pr-4 font-medium">Streaming</th>
                <th className="py-2 pr-4 font-medium">Compare</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredModels.map((m) => {
                const key = `${m.provider}:${m.name}`;
                const checked = selectedModels.includes(key);
                return (
                  <tr key={key} data-seeded={demo}>
                    <td className="py-2 pr-4 font-mono text-xs">{m.provider}</td>
                    <td className="py-2 pr-4 font-medium">{m.name}</td>
                    <td className="py-2 pr-4 text-muted-foreground">
                      {m.context.toLocaleString()}
                    </td>
                    <td className="py-2 pr-4 font-mono text-xs">
                      ${(m.input_cost * 1_000_000).toFixed(2)}
                    </td>
                    <td className="py-2 pr-4 font-mono text-xs">
                      ${(m.output_cost * 1_000_000).toFixed(2)}
                    </td>
                    <td className="py-2 pr-4">
                      {m.supports_streaming ? (
                        <Badge variant="outline" className="text-[10px]">yes</Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">no</span>
                      )}
                    </td>
                    <td className="py-2 pr-4">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleModel(key)}
                        aria-label={`Compare ${m.name}`}
                      />
                    </td>
                  </tr>
                );
              })}
              {filteredModels.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-3 text-sm text-muted-foreground">
                    No models match the filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Compare</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            value={comparePrompt}
            onChange={(e) => setComparePrompt(e.target.value)}
            rows={3}
            placeholder="Prompt to compare across selected models..."
          />
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="text-muted-foreground">Selected:</span>
            {selectedModels.length === 0 ? (
              <span className="text-muted-foreground">none</span>
            ) : (
              selectedModels.map((m) => (
                <Badge key={m} variant="outline" className="font-mono text-[10px]">
                  {m}
                </Badge>
              ))
            )}
          </div>
          <Button onClick={handleCompare}>Run comparison</Button>
        </CardContent>
      </Card>
    </div>
  );
}
