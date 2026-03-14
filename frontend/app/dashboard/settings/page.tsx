"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { api, ProviderHealthInfo } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { UsageChart } from "@/components/dashboard/UsageChart";
import { MCPManager } from "@/components/MCPManager";
import { isDemoMode } from "@/lib/demo-data";

interface ApiKey {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
}

interface ProviderConfig {
  id: string;
  provider: string;
  api_key_masked: string;
  base_url: string;
  is_default: boolean;
  is_enabled: boolean;
  created_at: string;
}

interface CUStatus {
  steer_available: boolean;
  steer_version: string;
  drive_available: boolean;
  drive_version: string;
  tmux_available: boolean;
  tmux_version: string;
  macos_version: string;
  is_macos: boolean;
  platform: string;
  computer_use_ready: boolean;
  missing: string[];
  install_instructions: Record<string, string>;
  agent_backends: string[];
  xdotool_available?: boolean;
  tesseract_available?: boolean;
  scrot_available?: boolean;
  wmctrl_available?: boolean;
  xclip_available?: boolean;
  xvfb_available?: boolean;
  pyautogui_available?: boolean;
  wsl_available?: boolean;
}

const STATUS_COLORS: Record<string, string> = {
  healthy: "bg-green-500",
  degraded: "bg-yellow-500",
  unavailable: "bg-red-500",
};

const SUPPORTED_PROVIDERS = [
  { value: "openai", label: "OpenAI", placeholder: "sk-..." },
  { value: "anthropic", label: "Anthropic", placeholder: "sk-ant-..." },
  { value: "ollama", label: "Ollama (local)", placeholder: "No key needed" },
];

export default function SettingsPage() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyValue, setNewKeyValue] = useState("");
  const [totalTokens, setTotalTokens] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [providerHealth, setProviderHealth] = useState<ProviderHealthInfo[]>([]);
  const [defaultModel, setDefaultModel] = useState("");
  const [, setProviders] = useState<string[]>([]);
  const [cuStatus, setCuStatus] = useState<CUStatus | null>(null);

  // Provider config state
  const [providerConfigs, setProviderConfigs] = useState<ProviderConfig[]>([]);
  const [addingProvider, setAddingProvider] = useState(false);
  const [newProvider, setNewProvider] = useState("openai");
  const [newProviderKey, setNewProviderKey] = useState("");
  const [newProviderBaseUrl, setNewProviderBaseUrl] = useState("");
  const [savingProvider, setSavingProvider] = useState(false);

  useEffect(() => {
    if (isDemoMode()) {
      setKeys([
        { id: "demo-key-1", name: "production", created_at: "2026-03-10T10:00:00Z", last_used_at: "2026-03-12T08:00:00Z" },
        { id: "demo-key-2", name: "development", created_at: "2026-03-11T14:00:00Z", last_used_at: null },
      ]);
      setTotalTokens(482_350);
      setProviderHealth([
        { provider: "openai", status: "healthy", latency_ms: 120, error: null },
      ]);
      setDefaultModel("gpt-4o-mini");
      setProviders(["openai"]);
      setProviderConfigs([
        { id: "demo-pc-1", provider: "openai", api_key_masked: "sk-proj...A4xB", base_url: "", is_default: true, is_enabled: true, created_at: "2026-03-10T10:00:00Z" },
      ]);
      setCuStatus({
        steer_available: false, steer_version: "", drive_available: false, drive_version: "",
        tmux_available: true, tmux_version: "3.4", macos_version: "15.3", is_macos: true,
        platform: "macos", computer_use_ready: false, missing: ["steer", "drive"],
        install_instructions: { steer: "brew install disler/tap/steer", drive: "brew install disler/tap/drive" },
        agent_backends: [],
      });
      return;
    }
    loadData();
  }, []);

  async function loadData() {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      const [keyList, stats, providerInfo, health] = await Promise.all([
        api.keys.list(data.session.access_token),
        api.stats.get(data.session.access_token),
        api.providers.list(data.session.access_token),
        api.providers.health(data.session.access_token).catch(() => [] as ProviderHealthInfo[]),
      ]);
      setKeys(keyList);
      setTotalTokens(stats.total_tokens);
      setDefaultModel(providerInfo.default_model);
      setProviders(providerInfo.providers);
      setProviderHealth(health);

      // Load provider configs
      try {
        const configs = await api.providers.configs(data.session.access_token);
        setProviderConfigs(configs);
      } catch {
        // endpoint may not exist on older backends
      }

      // Load computer use status
      try {
        const cu = await api.computerUse.status(data.session.access_token);
        setCuStatus(cu as unknown as CUStatus);
      } catch {
        // Computer use endpoint may not exist on older backends
      }
    } catch {
      // API may not be running
    }
  }

  async function createKey() {
    if (!newKeyName.trim()) return;
    setLoading(true);

    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      const result = await api.keys.create(newKeyName, data.session.access_token);
      setNewKeyValue(result.key);
      setNewKeyName("");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create key");
    } finally {
      setLoading(false);
    }
  }

  async function deleteKey(id: string) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      await api.keys.delete(id, data.session.access_token);
      setKeys(keys.filter((k) => k.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete key");
    }
  }

  async function saveProviderConfig() {
    setSavingProvider(true);
    setError("");
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      await api.providers.saveConfig(
        {
          provider: newProvider,
          api_key: newProviderKey || undefined,
          base_url: newProviderBaseUrl || undefined,
          is_default: providerConfigs.length === 0,
        },
        data.session.access_token,
      );
      setAddingProvider(false);
      setNewProviderKey("");
      setNewProviderBaseUrl("");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save provider");
    } finally {
      setSavingProvider(false);
    }
  }

  async function removeProvider(provider: string) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      await api.providers.deleteConfig(provider, data.session.access_token);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove provider");
    }
  }

  return (
    <div>
      <h1 className="text-3xl font-bold">Settings</h1>
      <p className="mt-1 text-muted-foreground">
        Manage providers, API keys, and view usage
      </p>

      {error && (
        <div className="mt-4 rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Provider Configuration */}
      <div className="mt-6">
        <h2 className="mb-3 text-lg font-semibold">Model Providers</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Add your own API keys to use AI models. Your keys are stored securely and never shared.
        </p>

        {/* Existing provider configs */}
        {providerConfigs.length > 0 ? (
          <div className="space-y-2 mb-4">
            {providerConfigs.map((config) => {
              const health = providerHealth.find((h) => h.provider === config.provider);
              const status = health?.status || "unknown";
              return (
                <div
                  key={config.provider}
                  className="flex items-center justify-between rounded-lg border border-border bg-card p-3"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`h-2.5 w-2.5 rounded-full ${STATUS_COLORS[status] || "bg-gray-500"}`}
                    />
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium capitalize">{config.provider}</p>
                        {config.is_default && (
                          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                            default
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground font-mono">
                        {config.api_key_masked}
                        {config.base_url && ` · ${config.base_url}`}
                      </p>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => removeProvider(config.provider)}
                  >
                    Remove
                  </Button>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="mb-4 rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-4">
            <p className="text-sm text-yellow-400">
              No providers configured yet. Add an API key below to start using AI models.
            </p>
          </div>
        )}

        {/* Add provider form */}
        {addingProvider ? (
          <div className="rounded-lg border border-border bg-card p-4 space-y-3">
            <div className="flex gap-2">
              <select
                value={newProvider}
                onChange={(e) => setNewProvider(e.target.value)}
                className="h-9 rounded-md border border-border bg-background px-3 text-sm"
              >
                {SUPPORTED_PROVIDERS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
                <option value="groq">Groq</option>
                <option value="together">Together AI</option>
                <option value="fireworks">Fireworks AI</option>
              </select>
              <Input
                placeholder={SUPPORTED_PROVIDERS.find((p) => p.value === newProvider)?.placeholder || "API key"}
                type="password"
                value={newProviderKey}
                onChange={(e) => setNewProviderKey(e.target.value)}
                className="flex-1"
              />
            </div>
            {(newProvider === "ollama" || !SUPPORTED_PROVIDERS.find((p) => p.value === newProvider)) && (
              <Input
                placeholder="Base URL (e.g., http://localhost:11434)"
                value={newProviderBaseUrl}
                onChange={(e) => setNewProviderBaseUrl(e.target.value)}
              />
            )}
            <div className="flex gap-2">
              <Button onClick={saveProviderConfig} disabled={savingProvider || (!newProviderKey && newProvider !== "ollama")}>
                {savingProvider ? "Saving..." : "Save"}
              </Button>
              <Button variant="ghost" onClick={() => { setAddingProvider(false); setNewProviderKey(""); setNewProviderBaseUrl(""); }}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <Button variant="outline" size="sm" onClick={() => setAddingProvider(true)}>
            + Add Provider
          </Button>
        )}

        {defaultModel && (
          <p className="mt-3 text-xs text-muted-foreground">
            Default model: <span className="font-mono">{defaultModel}</span>
          </p>
        )}
      </div>

      {/* Computer Use */}
      {cuStatus && (
        <div className="mt-8">
          <h2 className="mb-3 text-lg font-semibold">Computer Use</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { name: "Steer (GUI)", available: cuStatus.steer_available, version: cuStatus.steer_version },
              { name: "Drive (Terminal)", available: cuStatus.drive_available, version: cuStatus.drive_version },
              { name: "tmux", available: cuStatus.tmux_available, version: cuStatus.tmux_version },
              { name: "macOS", available: cuStatus.is_macos, version: cuStatus.macos_version },
            ].map((comp) => (
              <div
                key={comp.name}
                className="flex items-center gap-3 rounded-lg border border-border bg-card p-3"
              >
                <div
                  className={`h-2.5 w-2.5 rounded-full ${comp.available ? "bg-green-500" : "bg-red-500"}`}
                />
                <div className="flex-1">
                  <p className="text-sm font-medium">{comp.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {comp.available ? comp.version || "Installed" : "Missing"}
                  </p>
                </div>
              </div>
            ))}
          </div>
          {cuStatus.missing.length > 0 && (
            <div className="mt-3 rounded-lg border border-yellow-500/30 bg-yellow-500/5 p-3">
              <p className="text-sm font-medium text-yellow-500">Missing components:</p>
              {Object.entries(cuStatus.install_instructions).map(([key, instruction]) => (
                <div key={key} className="mt-1">
                  <p className="text-xs text-muted-foreground font-mono">{instruction}</p>
                </div>
              ))}
            </div>
          )}
          <p className="mt-2 text-xs text-muted-foreground">
            Platform: <span className="font-mono">{cuStatus.platform || "unknown"}</span>
            {" — "}
            {cuStatus.computer_use_ready
              ? "All components installed — computer use nodes available in blueprints."
              : "Install missing components to enable computer use in blueprints."}
          </p>
          {cuStatus.agent_backends && cuStatus.agent_backends.length > 0 && (
            <div className="mt-3">
              <p className="text-sm font-medium mb-2">Agent Backends (Agent-on-Agent)</p>
              <div className="flex flex-wrap gap-2">
                {cuStatus.agent_backends.map((b) => (
                  <span key={b} className="rounded-full border border-orange-500/30 bg-orange-500/5 px-2 py-0.5 text-xs font-medium text-orange-400">
                    {b}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* MCP Connections */}
      <div className="mt-8">
        <MCPManager />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>API Keys</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Input
                placeholder="Key name (e.g., production)"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
              />
              <Button onClick={createKey} disabled={loading || !newKeyName.trim()}>
                Generate
              </Button>
            </div>

            {newKeyValue && (
              <div className="rounded-lg border border-primary/50 bg-primary/5 p-3">
                <p className="text-xs text-muted-foreground">
                  Copy this key now — it won&apos;t be shown again:
                </p>
                <code className="mt-1 block break-all text-sm">{newKeyValue}</code>
              </div>
            )}

            {keys.length === 0 ? (
              <p className="text-sm text-muted-foreground">No API keys yet.</p>
            ) : (
              <div className="space-y-2">
                {keys.map((key) => (
                  <div
                    key={key.id}
                    className="flex items-center justify-between rounded-lg border border-border p-3"
                  >
                    <div>
                      <p className="text-sm font-medium">{key.name}</p>
                      <p className="text-xs text-muted-foreground">
                        Created {new Date(key.created_at).toLocaleDateString()}
                        {key.last_used_at &&
                          ` · Last used ${new Date(key.last_used_at).toLocaleDateString()}`}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => deleteKey(key.id)}
                    >
                      Delete
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <UsageChart totalTokens={totalTokens} />
      </div>
    </div>
  );
}
