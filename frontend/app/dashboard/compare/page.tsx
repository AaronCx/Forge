"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { api, ModelInfo, CompareResult } from "@/lib/api";
import { Button } from "@/components/ui/button";

export default function ComparePage() {
  const router = useRouter();
  const tokenRef = useRef("");

  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [prompt, setPrompt] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("You are a helpful assistant.");
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(1024);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<CompareResult[]>([]);

  useEffect(() => {
    async function load() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) {
        router.push("/login");
        return;
      }
      tokenRef.current = data.session.access_token;
      const modelList = await api.providers.models(data.session.access_token);
      setModels(modelList);
    }
    load();
  }, [router]);

  function toggleModel(modelId: string) {
    setSelectedModels((prev) =>
      prev.includes(modelId)
        ? prev.filter((m) => m !== modelId)
        : prev.length < 5
          ? [...prev, modelId]
          : prev,
    );
  }

  async function handleCompare() {
    if (selectedModels.length < 2 || !prompt.trim()) return;
    setRunning(true);
    setResults([]);
    try {
      const res = await api.compare.run(
        {
          prompt,
          system_prompt: systemPrompt,
          models: selectedModels,
          temperature,
          max_tokens: maxTokens,
        },
        tokenRef.current,
      );
      setResults(res.results);
    } catch {
      // Could add error toast
    } finally {
      setRunning(false);
    }
  }

  // Group models by provider
  const grouped = models.reduce<Record<string, ModelInfo[]>>((acc, m) => {
    (acc[m.provider] ||= []).push(m);
    return acc;
  }, {});

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">Model Comparison</h1>
      <p className="text-sm text-muted-foreground">
        Run the same prompt on multiple models side-by-side to compare quality, speed, and cost.
      </p>

      {/* Model selection */}
      <div className="rounded-lg border border-border bg-card p-4">
        <h3 className="mb-3 text-sm font-semibold">
          Select Models ({selectedModels.length}/5)
        </h3>
        {Object.entries(grouped).map(([provider, providerModels]) => (
          <div key={provider} className="mb-3">
            <p className="mb-1 text-xs font-medium uppercase text-muted-foreground">
              {provider}
            </p>
            <div className="flex flex-wrap gap-2">
              {providerModels.map((m) => (
                <button
                  key={m.id}
                  onClick={() => toggleModel(m.id)}
                  className={`rounded-md border px-3 py-1 text-xs transition-colors ${
                    selectedModels.includes(m.id)
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border text-muted-foreground hover:border-primary/50"
                  }`}
                >
                  {m.name}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Prompt */}
      <div className="space-y-3 rounded-lg border border-border bg-card p-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">
            System Prompt
          </label>
          <input
            type="text"
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">
            Prompt
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={4}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            placeholder="Enter your prompt here..."
          />
        </div>
        <div className="flex gap-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Temperature
            </label>
            <input
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={temperature}
              onChange={(e) => setTemperature(Number(e.target.value))}
              className="w-24 rounded-md border border-border bg-background px-2 py-1 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Max Tokens
            </label>
            <input
              type="number"
              min={1}
              max={16384}
              value={maxTokens}
              onChange={(e) => setMaxTokens(Number(e.target.value))}
              className="w-24 rounded-md border border-border bg-background px-2 py-1 text-sm"
            />
          </div>
        </div>
        <Button
          onClick={handleCompare}
          disabled={running || selectedModels.length < 2 || !prompt.trim()}
        >
          {running ? "Comparing..." : "Compare Models"}
        </Button>
      </div>

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-sm font-semibold">Results</h3>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {results.map((r, i) => (
              <div
                key={i}
                className={`rounded-lg border p-4 ${
                  r.error
                    ? "border-red-500/50 bg-red-500/5"
                    : "border-border bg-card"
                }`}
              >
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-semibold">{r.model}</span>
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                    {r.provider}
                  </span>
                </div>

                {r.error ? (
                  <p className="text-sm text-red-400">{r.error}</p>
                ) : (
                  <>
                    <div className="mb-3 max-h-48 overflow-y-auto whitespace-pre-wrap text-xs text-foreground/80">
                      {r.content}
                    </div>
                    <div className="grid grid-cols-3 gap-2 border-t border-border pt-2 text-[11px] text-muted-foreground">
                      <div>
                        <span className="block font-medium">Latency</span>
                        {(r.latency_ms / 1000).toFixed(1)}s
                      </div>
                      <div>
                        <span className="block font-medium">Tokens</span>
                        {r.input_tokens + r.output_tokens}
                      </div>
                      <div>
                        <span className="block font-medium">Cost</span>
                        ${r.cost.toFixed(4)}
                      </div>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
