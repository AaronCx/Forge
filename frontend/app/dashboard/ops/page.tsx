"use client";

import { Suspense, useCallback } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { LayoutGrid, List } from "lucide-react";

import { Button } from "@/components/ui/button";
import { OpsKanban } from "@/components/ops/OpsKanban";
import { RunHistory } from "@/components/dashboard/RunHistory";

/**
 * PR-5 Operations workspace home. Kanban board across run lifecycle columns
 * (Queued → Running → Awaiting Approval → Done / Failed). A list-view toggle
 * keeps the dense table available for power users.
 *
 * View persistence: ?view=board|list. useSearchParams runs inside a Suspense
 * boundary so the surrounding shell statically pre-renders.
 */
const VIEWS = ["board", "list"] as const;
type OpsView = (typeof VIEWS)[number];

export default function OpsPage() {
  return (
    <Suspense fallback={<OpsShell view="board" />}>
      <OpsContent />
    </Suspense>
  );
}

function OpsContent() {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const raw = params?.get("view") ?? "board";
  const view: OpsView = (VIEWS as readonly string[]).includes(raw) ? (raw as OpsView) : "board";

  const setView = useCallback(
    (next: OpsView) => {
      const url = new URL(window.location.href);
      url.searchParams.set("view", next);
      router.replace(`${pathname}?${url.searchParams.toString()}`, { scroll: false });
    },
    [pathname, router],
  );

  return <OpsShell view={view} onChange={setView} interactive />;
}

function OpsShell({
  view,
  onChange,
  interactive,
}: {
  view: OpsView;
  onChange?: (next: OpsView) => void;
  interactive?: boolean;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end justify-between gap-3">
        <header>
          <h1 className="text-2xl font-semibold tracking-tight">Operations</h1>
          <p className="text-sm text-muted-foreground">
            Live agent runs across the lifecycle. Click any card to inspect.
          </p>
        </header>

        <div
          className="inline-flex rounded-md border bg-card p-0.5 text-xs"
          role="group"
          aria-label="View toggle"
        >
          <Button
            size="sm"
            variant={view === "board" ? "default" : "ghost"}
            className="h-7 gap-1 px-2"
            onClick={() => onChange?.("board")}
            data-testid="ops-view-board"
          >
            <LayoutGrid className="h-3.5 w-3.5" aria-hidden />
            Board
          </Button>
          <Button
            size="sm"
            variant={view === "list" ? "default" : "ghost"}
            className="h-7 gap-1 px-2"
            onClick={() => onChange?.("list")}
            data-testid="ops-view-list"
          >
            <List className="h-3.5 w-3.5" aria-hidden />
            List
          </Button>
        </div>
      </div>

      {interactive ? (view === "board" ? <OpsKanban /> : <RunHistory />) : null}
    </div>
  );
}
