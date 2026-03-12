"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { UsageChart } from "@/components/dashboard/UsageChart";
import { isDemoMode } from "@/lib/demo-data";

interface ApiKey {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
}

export default function SettingsPage() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyValue, setNewKeyValue] = useState("");
  const [totalTokens, setTotalTokens] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isDemoMode()) {
      setKeys([
        { id: "demo-key-1", name: "production", created_at: "2026-03-10T10:00:00Z", last_used_at: "2026-03-12T08:00:00Z" },
        { id: "demo-key-2", name: "development", created_at: "2026-03-11T14:00:00Z", last_used_at: null },
      ]);
      setTotalTokens(482_350);
      return;
    }
    loadData();
  }, []);

  async function loadData() {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      const [keyList, stats] = await Promise.all([
        api.keys.list(data.session.access_token),
        api.stats.get(data.session.access_token),
      ]);
      setKeys(keyList);
      setTotalTokens(stats.total_tokens);
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
    } catch {
      // handle error
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
    } catch {
      // handle error
    }
  }

  return (
    <div>
      <h1 className="text-3xl font-bold">Settings</h1>
      <p className="mt-1 text-muted-foreground">
        Manage API keys and view usage
      </p>

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
