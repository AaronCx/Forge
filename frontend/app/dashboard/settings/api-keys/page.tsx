"use client";

import { useEffect, useState } from "react";
import { Key } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { isDemoMode, DEMO_API_KEYS_DETAILED } from "@/lib/demo-data";
import { api } from "@/lib/api";
import { supabase } from "@/lib/supabase";

interface ApiKeyRow {
  id: string;
  name: string;
  masked: string;
  created_at: string;
  last_used_at: string | null;
}

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeyRow[]>([]);
  const [demo, setDemo] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (isDemoMode()) {
      setDemo(true);
      setKeys(DEMO_API_KEYS_DETAILED);
      return;
    }
    async function load() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) return;
      try {
        const list = await api.keys.list(data.session.access_token);
        setKeys(
          list.map((k) => ({
            id: k.id,
            name: k.name,
            masked: "fge_•••• ••••",
            created_at: k.created_at,
            last_used_at: k.last_used_at,
          }))
        );
      } catch {
        // ignore
      }
    }
    load();
  }, []);

  async function handleCreate() {
    if (demo) {
      toast("Demo mode — sign in to create API keys");
      setDialogOpen(false);
      return;
    }
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const { data } = await supabase.auth.getSession();
      if (!data.session) return;
      const result = await api.keys.create(newName.trim(), data.session.access_token);
      toast.success("API key created", {
        description: result.key,
      });
      setNewName("");
      setDialogOpen(false);
      const list = await api.keys.list(data.session.access_token);
      setKeys(
        list.map((k) => ({
          id: k.id,
          name: k.name,
          masked: "fge_•••• ••••",
          created_at: k.created_at,
          last_used_at: k.last_used_at,
        }))
      );
    } catch {
      toast.error("Failed to create API key");
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(id: string) {
    if (demo) {
      toast("Demo mode — keys are read-only");
      return;
    }
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;
    try {
      await api.keys.delete(id, data.session.access_token);
      setKeys((prev) => prev.filter((k) => k.id !== id));
      toast.success("API key revoked");
    } catch {
      toast.error("Failed to revoke API key");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3">
        <Key className="mt-1 h-6 w-6 text-muted-foreground" aria-hidden="true" />
        <div>
          <h1 className="text-3xl font-bold">API Keys</h1>
          <p className="mt-1 text-muted-foreground">
            Manage API keys for accessing Forge from external systems.
          </p>
        </div>
      </div>

      <div className="flex justify-end">
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button>+ New API key</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create API key</DialogTitle>
              <DialogDescription>
                Give the key a memorable name. Forge will display the secret once on creation.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="key-name">Name</Label>
                <Input
                  id="key-name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="ci-pipeline"
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleCreate} disabled={creating || !newName.trim()}>
                {creating ? "Creating..." : "Create"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Active keys</CardTitle>
        </CardHeader>
        <CardContent>
          {keys.length === 0 ? (
            <p className="text-sm text-muted-foreground">No API keys yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Name</th>
                  <th className="py-2 pr-4 font-medium">Key</th>
                  <th className="py-2 pr-4 font-medium">Created</th>
                  <th className="py-2 pr-4 font-medium">Last used</th>
                  <th className="py-2 pr-4 font-medium" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {keys.map((k) => (
                  <tr key={k.id} data-seeded={demo}>
                    <td className="py-2 pr-4 font-medium">{k.name}</td>
                    <td className="py-2 pr-4 font-mono text-xs">{k.masked}</td>
                    <td className="py-2 pr-4 text-xs text-muted-foreground">
                      {new Date(k.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-2 pr-4 text-xs text-muted-foreground">
                      {k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="py-2 pr-4 text-right">
                      <Button size="sm" variant="ghost" onClick={() => handleRevoke(k.id)}>
                        Revoke
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
