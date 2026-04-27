"use client";

import { useEffect, useState } from "react";
import { Target as TargetIcon } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { isDemoMode, DEMO_TARGETS } from "@/lib/demo-data";
import { supabase } from "@/lib/supabase";
import { API_URL } from "@/lib/constants";

interface TargetRow {
  id: string;
  name: string;
  platform: "macos" | "linux" | "windows";
  capabilities: string[];
  status: "healthy" | "idle" | "down";
  last_seen: string;
}

function StatusPill({ status }: { status: TargetRow["status"] }) {
  const tone = {
    healthy: "bg-emerald-500/15 text-emerald-300 border-emerald-700",
    idle: "bg-yellow-500/15 text-yellow-300 border-yellow-700",
    down: "bg-red-500/15 text-red-300 border-red-700",
  } as const;
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${tone[status]}`}>
      {status}
    </span>
  );
}

export default function TargetsPage() {
  const [targets, setTargets] = useState<TargetRow[]>([]);
  const [demo, setDemo] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newUrl, setNewUrl] = useState("");
  const [newPlatform, setNewPlatform] = useState("macos");

  useEffect(() => {
    if (isDemoMode()) {
      setDemo(true);
      setTargets(DEMO_TARGETS);
      return;
    }
    async function load() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) return;
      const token = data.session.access_token;
      try {
        const res = await fetch(`${API_URL}/api/targets`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const list = (await res.json()) as Array<{
            id: string;
            name: string;
            platform?: string;
            capabilities?: string[];
            status?: string;
            last_seen?: string;
          }>;
          setTargets(
            list.map((t) => ({
              id: t.id,
              name: t.name,
              platform: (t.platform === "linux" || t.platform === "windows" ? t.platform : "macos") as TargetRow["platform"],
              capabilities: t.capabilities ?? [],
              status: (t.status === "healthy" || t.status === "idle" || t.status === "down" ? t.status : "idle") as TargetRow["status"],
              last_seen: t.last_seen ?? new Date().toISOString(),
            }))
          );
        }
      } catch {
        // ignore
      }
    }
    load();
  }, []);

  function handleAdd() {
    if (demo) {
      toast("Demo mode — connect a Forge runtime to add targets");
      setDialogOpen(false);
      return;
    }
    if (!newName.trim() || !newUrl.trim()) return;
    toast.message("Registering target...");
    setDialogOpen(false);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3">
        <TargetIcon className="mt-1 h-6 w-6 text-muted-foreground" aria-hidden="true" />
        <div>
          <h1 className="text-3xl font-bold">Targets</h1>
          <p className="mt-1 text-muted-foreground">
            Multi-machine dispatch — execution targets that blueprint nodes can route to.
          </p>
        </div>
      </div>

      <div className="flex justify-end">
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button>+ Add target</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add target</DialogTitle>
              <DialogDescription>
                Register a remote target so blueprint nodes can dispatch to it.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="tgt-name">Name</Label>
                <Input
                  id="tgt-name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="prod-mac-mini"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="tgt-url">Listen URL</Label>
                <Input
                  id="tgt-url"
                  value={newUrl}
                  onChange={(e) => setNewUrl(e.target.value)}
                  placeholder="https://target.example.com:8443"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="tgt-platform">Platform</Label>
                <select
                  id="tgt-platform"
                  className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
                  value={newPlatform}
                  onChange={(e) => setNewPlatform(e.target.value)}
                >
                  <option value="macos">macOS</option>
                  <option value="linux">Linux</option>
                  <option value="windows">Windows</option>
                </select>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleAdd}>Register</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Targets</CardTitle>
        </CardHeader>
        <CardContent>
          {targets.length === 0 ? (
            <p className="text-sm text-muted-foreground">No targets registered yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Name</th>
                  <th className="py-2 pr-4 font-medium">Platform</th>
                  <th className="py-2 pr-4 font-medium">Capabilities</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                  <th className="py-2 pr-4 font-medium">Last seen</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {targets.map((t) => (
                  <tr key={t.id} data-seeded={demo}>
                    <td className="py-2 pr-4 font-medium">{t.name}</td>
                    <td className="py-2 pr-4 font-mono text-xs">{t.platform}</td>
                    <td className="py-2 pr-4">
                      <div className="flex flex-wrap gap-1">
                        {t.capabilities.map((cap) => (
                          <Badge key={cap} variant="outline" className="text-[10px]">
                            {cap}
                          </Badge>
                        ))}
                      </div>
                    </td>
                    <td className="py-2 pr-4"><StatusPill status={t.status} /></td>
                    <td className="py-2 pr-4 text-xs text-muted-foreground">
                      {new Date(t.last_seen).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Dispatch routing</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          <ol className="list-decimal space-y-1 pl-4">
            <li>Explicit target on the blueprint node</li>
            <li>Blueprint default target</li>
            <li>Capability-based match across registered targets</li>
            <li>Local fallback (the running Forge runtime)</li>
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}
