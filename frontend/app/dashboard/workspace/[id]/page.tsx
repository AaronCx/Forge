"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getToken } from "@/lib/auth-client";
import { api, Workspace } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { isDemoMode, DEMO_WORKSPACES } from "@/lib/demo-data";

export default function WorkspaceIDEPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isDemoMode()) {
      const ws = (DEMO_WORKSPACES as Workspace[]).find((w) => w.id === id);
      setWorkspace(ws || null);
      setLoading(false);
      return;
    }
    async function load() {
      const token = await getToken();
      if (!token) return;
      try {
        const ws = await api.workspaces.get(id, token);
        setWorkspace(ws);
      } catch {
        setWorkspace(null);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  if (loading) {
    return (
      <div className="flex h-[calc(100vh-8rem)] items-center justify-center text-muted-foreground">
        Loading workspace...
      </div>
    );
  }

  if (!workspace) {
    return (
      <div className="flex h-[calc(100vh-8rem)] flex-col items-center justify-center gap-4">
        <p className="text-muted-foreground">Workspace not found.</p>
        <Button variant="outline" onClick={() => router.push("/dashboard/workspace")}>
          Back to Workspaces
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col -mx-4 md:-mx-8 -mt-4 md:-mt-8">
      {/* Toolbar */}
      <div className="flex items-center gap-3 border-b border-border bg-card px-4 py-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push("/dashboard/workspace")}
        >
          &larr; Back
        </Button>
        <div className="h-4 w-px bg-border" />
        <span className="text-sm font-semibold">{workspace.name}</span>
        <span className="text-xs text-muted-foreground">{workspace.path}</span>
      </div>

      {/* Three-panel layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar - File Tree */}
        <div className="flex w-[250px] shrink-0 flex-col border-r border-border bg-card">
          <div className="border-b border-border px-3 py-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              File Tree
            </span>
          </div>
          <div className="flex flex-1 items-center justify-center p-4 text-center text-xs text-muted-foreground">
            File explorer will appear here
          </div>
        </div>

        {/* Center - Editor */}
        <div className="flex flex-1 flex-col bg-background">
          <div className="border-b border-border px-3 py-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Editor
            </span>
          </div>
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
            Select a file to edit
          </div>
        </div>
      </div>
    </div>
  );
}
