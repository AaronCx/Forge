"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Video } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { isDemoMode, DEMO_RECORDINGS } from "@/lib/demo-data";
import { supabase } from "@/lib/supabase";
import { API_URL } from "@/lib/constants";

interface RecordingRow {
  id: string;
  blueprint: string;
  target: string;
  duration_ms: number;
  started_at: string;
  trace_id: string;
  thumbnail_caption: string;
}

function formatDuration(ms: number) {
  const total = Math.round(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function RecordingsPage() {
  const [recordings, setRecordings] = useState<RecordingRow[]>([]);
  const [demo, setDemo] = useState(false);
  const [active, setActive] = useState<RecordingRow | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (isDemoMode()) {
      setDemo(true);
      setRecordings(DEMO_RECORDINGS);
      setActive(DEMO_RECORDINGS[0] ?? null);
      return;
    }
    async function load() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) return;
      try {
        const res = await fetch(`${API_URL}/api/recordings`, {
          headers: { Authorization: `Bearer ${data.session.access_token}` },
        });
        if (res.ok) {
          const list = (await res.json()) as RecordingRow[];
          setRecordings(list);
          setActive(list[0] ?? null);
        }
      } catch {
        // backend may not yet expose recordings
      }
    }
    load();
  }, []);

  const filtered = recordings.filter((r) => {
    const q = filter.toLowerCase();
    return (
      !q ||
      r.blueprint.toLowerCase().includes(q) ||
      r.target.toLowerCase().includes(q)
    );
  });

  function handleExport() {
    if (demo) {
      toast("Demo mode — export disabled", {
        description: "Connect a Forge runtime to export recording files.",
      });
      return;
    }
    toast.message("Export starting...");
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3">
        <Video className="mt-1 h-6 w-6 text-muted-foreground" aria-hidden="true" />
        <div>
          <h1 className="text-3xl font-bold">Recordings</h1>
          <p className="mt-1 text-muted-foreground">
            Screen recordings from Computer Use sessions.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-sm font-medium">Player</CardTitle>
            <Button size="sm" variant="outline" onClick={handleExport}>
              Export
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {active ? (
            <div className="space-y-3">
              <div className="relative aspect-video w-full overflow-hidden rounded bg-gradient-to-br from-slate-800 via-slate-900 to-slate-950">
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center text-muted-foreground">
                  <Video className="h-10 w-10 opacity-60" aria-hidden="true" />
                  <p className="text-sm">{active.thumbnail_caption}</p>
                </div>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{active.blueprint}</Badge>
                  <Badge variant="outline">{active.target}</Badge>
                  <span className="text-muted-foreground">{formatDuration(active.duration_ms)}</span>
                </div>
                <Link href={`/dashboard/traces/${active.trace_id}`}>
                  <Button variant="ghost" size="sm">
                    Jump to trace →
                  </Button>
                </Link>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No recording selected.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-sm font-medium">Gallery</CardTitle>
            <input
              type="search"
              placeholder="Filter by blueprint or target..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="h-8 w-48 rounded border border-input bg-transparent px-2 text-xs"
            />
          </div>
        </CardHeader>
        <CardContent>
          {filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground">No recordings match the filter.</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {filtered.map((rec) => (
                <button
                  key={rec.id}
                  onClick={() => setActive(rec)}
                  data-seeded={demo}
                  className={`group rounded-lg border p-3 text-left transition-colors ${
                    active?.id === rec.id ? "border-primary" : "border-border hover:border-primary/50"
                  }`}
                >
                  <div className="aspect-video rounded bg-gradient-to-br from-slate-800 to-slate-950" />
                  <p className="mt-2 truncate text-sm">{rec.blueprint}</p>
                  <p className="text-xs text-muted-foreground">
                    {rec.target} · {formatDuration(rec.duration_ms)}
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    {new Date(rec.started_at).toLocaleString()}
                  </p>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
