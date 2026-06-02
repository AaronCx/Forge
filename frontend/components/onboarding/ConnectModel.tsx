"use client";

import { useState } from "react";
import { Loader2, Cloud, HardDrive, Server } from "lucide-react";
import { api, type ProviderKind, type ProviderVerifyBody } from "@/lib/api";
import { getToken } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface ConnectModelProps {
  onConnected: () => void;
  onSkip: () => void;
}

type Model = { id: string; name: string };

/**
 * Onboarding "connect a model" step — cloud, local (Ollama), or a custom
 * OpenAI-compatible endpoint. Skippable. Verify before connect; the model
 * picker appears once verification returns models.
 */
export function ConnectModel({ onConnected, onSkip }: ConnectModelProps) {
  const [tab, setTab] = useState<ProviderKind>("cloud");
  const [cloudProvider, setCloudProvider] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [ollamaUrl, setOllamaUrl] = useState("http://localhost:11434");
  const [genericUrl, setGenericUrl] = useState("");
  const [genericKey, setGenericKey] = useState("");

  const [models, setModels] = useState<Model[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");

  const bodyForTab = (): ProviderVerifyBody => {
    if (tab === "cloud") return { kind: "cloud", provider: cloudProvider, api_key: apiKey };
    if (tab === "ollama") return { kind: "ollama", base_url: ollamaUrl };
    return { kind: "generic", base_url: genericUrl, api_key: genericKey || undefined };
  };

  const resetVerification = () => {
    setModels([]);
    setSelectedModel("");
    setError("");
  };

  const verify = async () => {
    resetVerification();
    setVerifying(true);
    try {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated.");
      const result = await api.providers.verify(bodyForTab(), token);
      if (!result.ok) {
        setError(result.error || "Verification failed.");
        return;
      }
      const found = result.models ?? [];
      setModels(found);
      if (found.length > 0) setSelectedModel(found[0].id);
      if (found.length === 0) setError("Connected, but no models were found.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed.");
    } finally {
      setVerifying(false);
    }
  };

  const connect = async () => {
    setConnecting(true);
    setError("");
    try {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated.");
      await api.providers.connect({ ...bodyForTab(), model: selectedModel }, token);
      onConnected();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect.");
    } finally {
      setConnecting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-semibold">Connect a model</h2>
          <p className="text-sm text-muted-foreground">
            Use a cloud provider, a local model, or your own endpoint. You can change this later.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={onSkip}>
          Skip
        </Button>
      </div>

      <Tabs
        value={tab}
        onValueChange={(v) => {
          setTab(v as ProviderKind);
          resetVerification();
        }}
      >
        <TabsList>
          <TabsTrigger value="cloud">
            <Cloud className="mr-1 h-4 w-4" /> Cloud
          </TabsTrigger>
          <TabsTrigger value="ollama">
            <HardDrive className="mr-1 h-4 w-4" /> Local
          </TabsTrigger>
          <TabsTrigger value="generic">
            <Server className="mr-1 h-4 w-4" /> Custom
          </TabsTrigger>
        </TabsList>

        <TabsContent value="cloud" className="space-y-3 pt-3">
          <div className="space-y-1">
            <Label>Provider</Label>
            <select
              className="flex h-9 w-full rounded-md border bg-transparent px-3 text-sm"
              value={cloudProvider}
              onChange={(e) => {
                setCloudProvider(e.target.value);
                resetVerification();
              }}
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
            </select>
          </div>
          <div className="space-y-1">
            <Label>API key</Label>
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-…"
            />
          </div>
        </TabsContent>

        <TabsContent value="ollama" className="space-y-3 pt-3">
          <p className="text-sm text-muted-foreground">
            Runs on your machine, no API key, nothing leaves your network.
          </p>
          <p className="text-xs text-muted-foreground">
            Detection requires this Forge backend to run on your machine (it reads your localhost).
          </p>
          <div className="space-y-1">
            <Label>Ollama URL</Label>
            <Input value={ollamaUrl} onChange={(e) => setOllamaUrl(e.target.value)} />
          </div>
        </TabsContent>

        <TabsContent value="generic" className="space-y-3 pt-3">
          <p className="text-sm text-muted-foreground">
            Any OpenAI-compatible endpoint (LM Studio, vLLM, Groq, Together…).
          </p>
          <div className="space-y-1">
            <Label>Base URL</Label>
            <Input
              value={genericUrl}
              onChange={(e) => setGenericUrl(e.target.value)}
              placeholder="http://localhost:1234/v1"
            />
          </div>
          <div className="space-y-1">
            <Label>API key (optional)</Label>
            <Input type="password" value={genericKey} onChange={(e) => setGenericKey(e.target.value)} />
          </div>
        </TabsContent>
      </Tabs>

      <div className="flex items-center gap-2">
        <Button variant="outline" onClick={verify} disabled={verifying || connecting}>
          {verifying ? (
            <>
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              {tab === "ollama" ? "Detecting…" : "Verifying…"}
            </>
          ) : tab === "ollama" ? (
            "Detect local models"
          ) : (
            "Verify"
          )}
        </Button>
      </div>

      {models.length > 0 && (
        <div className="space-y-1">
          <Label>Model</Label>
          <select
            aria-label="Model"
            className="flex h-9 w-full rounded-md border bg-transparent px-3 text-sm"
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <Button onClick={connect} disabled={connecting || !selectedModel}>
          {connecting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
          Connect & continue
        </Button>
      </div>
    </div>
  );
}
