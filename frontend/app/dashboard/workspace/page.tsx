"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/auth-client";
import { api, Workspace } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { isDemoMode, DEMO_WORKSPACE, DEMO_WORKSPACE_ID } from "@/lib/demo-data";

export default function WorkspacesPage() {
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");

  useEffect(() => {
    if (isDemoMode()) {
      // Demo has a single seeded workspace — drop the visitor straight into the IDE.
      router.replace(`/dashboard/workspace/${DEMO_WORKSPACE_ID}`);
      setWorkspaces([DEMO_WORKSPACE as Workspace]);
      setLoading(false);
      return;
    }
    async function load() {
      const token = await getToken();
      if (!token) return;
      try {
        const data = await api.workspaces.list(token);
        setWorkspaces(data);
      } catch {
        setError("Failed to load workspaces. Check your connection.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [router]);

  async function handleCreate() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      if (isDemoMode()) {
        const demoWs: Workspace = {
          id: `ws-demo-${Date.now()}`,
          user_id: "demo",
          name: newName.trim(),
          description: newDescription.trim(),
          path: `/workspaces/${newName.trim().toLowerCase().replace(/\s+/g, "-")}`,
          status: "active",
          settings: {},
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        setWorkspaces((prev) => [demoWs, ...prev]);
      } else {
        const token = await getToken();
        if (!token) return;
        const ws = await api.workspaces.create(
          { name: newName.trim(), description: newDescription.trim() || undefined },
          token
        );
        setWorkspaces((prev) => [ws, ...prev]);
      }
      setNewName("");
      setNewDescription("");
      setDialogOpen(false);
    } catch {
      setError("Failed to create workspace.");
    } finally {
      setCreating(false);
    }
  }

  function formatDate(dateStr: string) {
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return (
    <div>
      {error && (
        <div className="mb-4 rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Workspaces</h1>
          <p className="mt-1 text-muted-foreground">
            Manage your project workspaces and files
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button>New Workspace</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Workspace</DialogTitle>
              <DialogDescription>
                Create a new workspace to organize your files and agents.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="ws-name">Name</Label>
                <Input
                  id="ws-name"
                  placeholder="My Project"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleCreate();
                  }}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="ws-desc">Description (optional)</Label>
                <Input
                  id="ws-desc"
                  placeholder="A brief description of this workspace"
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleCreate();
                  }}
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

      {loading ? (
        <p className="mt-8 text-muted-foreground">Loading workspaces...</p>
      ) : workspaces.length > 0 ? (
        <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {workspaces.map((ws) => (
            <Link key={ws.id} href={`/dashboard/workspace/${ws.id}`}>
              <Card className="cursor-pointer transition-colors hover:border-primary/50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-lg">{ws.name}</CardTitle>
                  {ws.description && (
                    <CardDescription className="line-clamp-2">
                      {ws.description}
                    </CardDescription>
                  )}
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span className="truncate font-mono" title={ws.path}>
                      {ws.path}
                    </span>
                    <span className="ml-2 shrink-0">
                      {formatDate(ws.updated_at)}
                    </span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <div className="mt-8 rounded-lg border border-dashed border-border p-12 text-center">
          <h3 className="text-lg font-semibold">No workspaces yet</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            Create your first workspace to get started.
          </p>
          <Button className="mt-4" onClick={() => setDialogOpen(true)}>
            New Workspace
          </Button>
        </div>
      )}
    </div>
  );
}
