"use client";

import { useEffect, useState } from "react";
import { Monitor } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  isDemoMode,
  DEMO_CU_CAPABILITY,
  DEMO_CU_SESSIONS,
  DEMO_CU_AUDIT,
  DEMO_CU_SAFETY,
  DEMO_CU_SCREENSHOTS,
} from "@/lib/demo-data";
import { supabase } from "@/lib/supabase";
import { API_URL } from "@/lib/constants";

interface CapabilityRow {
  platform: "macos" | "linux" | "windows";
  steer: "ok" | "missing" | "n/a";
  drive: "ok" | "missing" | "n/a";
  ocr: "ok" | "missing" | "n/a";
  notes: string;
}

interface AuditEntry {
  ts: string;
  action: string;
  target: string;
  blueprint: string;
  result: string;
  note?: string;
}

interface SessionEntry {
  id: string;
  target: string;
  kind: string;
  focus: string;
  started_at: string;
}

interface ScreenshotEntry {
  id: string;
  ts: string;
  target: string;
  thumb_caption: string;
}

function StatusPill({ value }: { value: "ok" | "missing" | "n/a" }) {
  const map = {
    ok: "bg-emerald-500/15 text-emerald-300 border-emerald-700",
    missing: "bg-red-500/15 text-red-300 border-red-700",
    "n/a": "bg-muted text-muted-foreground border-border",
  } as const;
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${map[value]}`}
    >
      {value}
    </span>
  );
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleString();
}

export default function ComputerUsePage() {
  const [capability, setCapability] = useState<CapabilityRow[]>([]);
  const [sessions, setSessions] = useState<SessionEntry[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [screenshots, setScreenshots] = useState<ScreenshotEntry[]>([]);
  const [seeded, setSeeded] = useState(false);

  useEffect(() => {
    if (isDemoMode()) {
      setCapability(DEMO_CU_CAPABILITY);
      setSessions(DEMO_CU_SESSIONS);
      setAudit(DEMO_CU_AUDIT);
      setScreenshots(DEMO_CU_SCREENSHOTS);
      setSeeded(true);
      return;
    }
    async function load() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) return;
      try {
        const res = await fetch(`${API_URL}/api/computer-use/status`, {
          headers: { Authorization: `Bearer ${data.session.access_token}` },
        });
        if (res.ok) {
          const status = await res.json();
          // Map a single-host status into the same shape as the multi-platform table.
          setCapability([
            {
              platform: status.platform ?? "macos",
              steer: status.steer_available ? "ok" : "missing",
              drive: status.drive_available ? "ok" : "missing",
              ocr: status.tmux_available ? "ok" : "missing",
              notes: `tmux ${status.tmux_version ?? "—"}`,
            },
          ]);
        }
      } catch {
        // Backend may be unreachable; render empty state
      }
    }
    load();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3">
        <Monitor className="mt-1 h-6 w-6 text-muted-foreground" aria-hidden="true" />
        <div>
          <h1 className="text-3xl font-bold">Computer Use</h1>
          <p className="mt-1 text-muted-foreground">
            Status and audit of the Steer (GUI) and Drive (Terminal) capability layer.
          </p>
        </div>
      </div>

      {seeded && (
        <div className="rounded-lg border border-yellow-700 bg-yellow-900/30 px-3 py-2 text-xs text-yellow-200" data-seeded="true">
          Connect a local Forge runtime to enable computer use. Demo data shown below.
        </div>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Capability report</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="py-2 pr-4 font-medium">Platform</th>
                <th className="py-2 pr-4 font-medium">Steer</th>
                <th className="py-2 pr-4 font-medium">Drive</th>
                <th className="py-2 pr-4 font-medium">OCR</th>
                <th className="py-2 pr-4 font-medium">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {capability.map((row) => (
                <tr key={row.platform} data-seeded={seeded}>
                  <td className="py-2 pr-4 font-mono">{row.platform}</td>
                  <td className="py-2 pr-4"><StatusPill value={row.steer} /></td>
                  <td className="py-2 pr-4"><StatusPill value={row.drive} /></td>
                  <td className="py-2 pr-4"><StatusPill value={row.ocr} /></td>
                  <td className="py-2 pr-4 text-muted-foreground">{row.notes}</td>
                </tr>
              ))}
              {capability.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-3 text-sm text-muted-foreground">
                    No capability data yet. Connect a Forge runtime to populate this report.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Active sessions</CardTitle>
        </CardHeader>
        <CardContent>
          {sessions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No active sessions.</p>
          ) : (
            <div className="space-y-2">
              {sessions.map((s) => (
                <div key={s.id} className="flex items-center justify-between rounded border border-border p-3 text-sm" data-seeded={seeded}>
                  <div>
                    <p className="font-medium">{s.target}</p>
                    <p className="text-xs text-muted-foreground">
                      <Badge variant="outline" className="mr-2">{s.kind}</Badge>
                      {s.focus}
                    </p>
                  </div>
                  <span className="text-xs text-muted-foreground">since {fmtTime(s.started_at)}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Audit log</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="py-2 pr-4 font-medium">Time</th>
                <th className="py-2 pr-4 font-medium">Action</th>
                <th className="py-2 pr-4 font-medium">Target</th>
                <th className="py-2 pr-4 font-medium">Blueprint</th>
                <th className="py-2 pr-4 font-medium">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {audit.map((row) => (
                <tr key={row.ts + row.action} data-seeded={seeded}>
                  <td className="py-2 pr-4 font-mono text-xs">{fmtTime(row.ts)}</td>
                  <td className="py-2 pr-4 font-mono">{row.action}</td>
                  <td className="py-2 pr-4">{row.target}</td>
                  <td className="py-2 pr-4 text-muted-foreground">{row.blueprint}</td>
                  <td className="py-2 pr-4">
                    <Badge variant={row.result === "ok" ? "default" : "destructive"}>
                      {row.result}
                    </Badge>
                    {row.note && (
                      <span className="ml-2 text-xs text-muted-foreground">{row.note}</span>
                    )}
                  </td>
                </tr>
              ))}
              {audit.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-3 text-sm text-muted-foreground">
                    No audit entries yet. Run a Computer Use blueprint to see actions here.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Safety config</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">App blocklist</dt>
              <dd className="mt-1 flex flex-wrap gap-1">
                {DEMO_CU_SAFETY.app_blocklist.map((app) => (
                  <Badge key={app} variant="outline" className="font-mono text-[10px]">{app}</Badge>
                ))}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">Command blocklist</dt>
              <dd className="mt-1 flex flex-wrap gap-1">
                {DEMO_CU_SAFETY.command_blocklist.map((cmd) => (
                  <Badge key={cmd} variant="outline" className="font-mono text-[10px]">{cmd}</Badge>
                ))}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">Rate limit</dt>
              <dd className="mt-1 font-mono text-sm">
                {DEMO_CU_SAFETY.rate_limit_per_minute} actions / minute
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">Approval gates</dt>
              <dd className="mt-1 flex flex-wrap gap-1">
                {DEMO_CU_SAFETY.approval_gates.map((gate) => (
                  <Badge key={gate} variant="outline" className="font-mono text-[10px]">{gate}</Badge>
                ))}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Recent screenshots</CardTitle>
        </CardHeader>
        <CardContent>
          {screenshots.length === 0 ? (
            <p className="text-sm text-muted-foreground">No screenshots yet.</p>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {screenshots.map((s) => (
                <div key={s.id} className="rounded border border-border p-2" data-seeded={seeded}>
                  <div className="aspect-video rounded bg-gradient-to-br from-slate-800 to-slate-900" />
                  <p className="mt-2 truncate text-xs">{s.thumb_caption}</p>
                  <p className="text-[10px] text-muted-foreground">{s.target} · {fmtTime(s.ts)}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
