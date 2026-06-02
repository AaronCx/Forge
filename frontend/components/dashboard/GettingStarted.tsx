"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Circle, X } from "lucide-react";
import { api, type Preferences } from "@/lib/api";
import { getToken } from "@/lib/auth-client";
import { useBackendMode } from "@/lib/backend-context";

type Item = {
  label: string;
  done: boolean;
  core: boolean;
  href?: string;
  onClick?: () => void;
};

function focusComposer() {
  const el = document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Command composer"]');
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.focus();
  }
}

/**
 * Dashboard "Getting started" checklist — the safety net for anyone who skipped
 * onboarding. Items are live-computed; the card auto-hides when the core items
 * are done or when dismissed (persisted to user_preferences). Live mode only.
 */
export function GettingStarted() {
  const { mode } = useBackendMode();
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [hasProvider, setHasProvider] = useState(false);
  const [hasAgent, setHasAgent] = useState(false);
  const [hasRun, setHasRun] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (mode !== "live") return;
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const [p, providers, agents, runs] = await Promise.all([
          api.preferences.get(token),
          api.providers.list(token).catch(() => ({ providers: [] as string[] })),
          api.agents.list(token).catch(() => []),
          api.runs.list(token).catch(() => []),
        ]);
        if (cancelled) return;
        setPrefs(p);
        setHasProvider((providers.providers?.length ?? 0) > 0);
        setHasAgent(agents.length > 0);
        setHasRun(runs.length > 0);
      } catch {
        // non-fatal — just don't show the checklist
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mode]);

  if (mode !== "live" || !loaded || dismissed) return null;
  if (prefs?.getting_started_dismissed) return null;

  const items: Item[] = [
    { label: "Connect a model", done: hasProvider, core: true, href: "/dashboard/connections" },
    { label: "Choose what you're working on", done: !!prefs?.use_case, core: false, href: "/onboarding" },
    { label: "Add an agent", done: hasAgent, core: true, href: "/dashboard/agents/new" },
    { label: "Run your first task", done: hasRun, core: true, onClick: focusComposer },
    { label: "Add custom instructions", done: !!prefs?.custom_instructions, core: false, href: "/onboarding" },
  ];

  // Auto-hide once the core items are all done.
  if (items.filter((i) => i.core).every((i) => i.done)) return null;

  const dismiss = async () => {
    setDismissed(true);
    try {
      const token = await getToken();
      if (token) await api.preferences.update({ getting_started_dismissed: true }, token);
    } catch {
      // best-effort — the card is already hidden for this session
    }
  };

  const doneCount = items.filter((i) => i.done).length;

  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm" data-testid="getting-started">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold">Getting started</h2>
          <p className="text-sm text-muted-foreground">
            {doneCount}/{items.length} done — finish setting up Forge.
          </p>
        </div>
        <button
          type="button"
          onClick={dismiss}
          className="text-muted-foreground hover:text-foreground"
          aria-label="Dismiss getting started"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <ul className="mt-3 space-y-1.5">
        {items.map((item) => {
          const icon = item.done ? (
            <CheckCircle2 className="h-4 w-4 text-green-500" />
          ) : (
            <Circle className="h-4 w-4 text-muted-foreground" />
          );
          const label = (
            <span className={`text-sm ${item.done ? "text-muted-foreground line-through" : ""}`}>{item.label}</span>
          );
          return (
            <li key={item.label} className="flex items-center gap-2">
              {icon}
              {item.done ? (
                label
              ) : item.href ? (
                <Link href={item.href} className="text-sm hover:underline">
                  {item.label}
                </Link>
              ) : (
                <button type="button" onClick={item.onClick} className="text-sm hover:underline">
                  {item.label}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
