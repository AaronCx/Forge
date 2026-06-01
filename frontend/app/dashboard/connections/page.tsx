"use client";

import { Suspense, useCallback } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import ProvidersPage from "../providers/page";
import McpPage from "../mcp/page";
import TargetsPage from "../targets/page";
import ComputerUsePage from "../computer-use/page";

const TABS = ["providers", "mcp", "targets", "computer-use"] as const;
type ConnectionsTab = (typeof TABS)[number];

export default function ConnectionsPage() {
  return (
    <Suspense fallback={<ConnectionsShell tab="providers" />}>
      <ConnectionsContent />
    </Suspense>
  );
}

function ConnectionsContent() {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const raw = params?.get("tab") ?? "providers";
  const tab: ConnectionsTab = (TABS as readonly string[]).includes(raw)
    ? (raw as ConnectionsTab)
    : "providers";

  const onChange = useCallback(
    (next: string) => {
      const url = new URL(window.location.href);
      url.searchParams.set("tab", next);
      router.replace(`${pathname}?${url.searchParams.toString()}`, { scroll: false });
    },
    [pathname, router],
  );

  return <ConnectionsShell tab={tab} onChange={onChange} interactive />;
}

function ConnectionsShell({
  tab,
  onChange,
  interactive,
}: {
  tab: ConnectionsTab;
  onChange?: (next: string) => void;
  interactive?: boolean;
}) {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Connections</h1>
        <p className="text-sm text-muted-foreground">
          Model providers, MCP servers, execution targets, and Computer-Use configuration.
        </p>
      </header>

      <Tabs value={tab} onValueChange={onChange ?? (() => {})}>
        <TabsList>
          <TabsTrigger value="providers">Providers</TabsTrigger>
          <TabsTrigger value="mcp">MCP</TabsTrigger>
          <TabsTrigger value="targets">Targets</TabsTrigger>
          <TabsTrigger value="computer-use">Computer Use</TabsTrigger>
        </TabsList>

        {interactive && (
          <>
            <TabsContent value="providers">
              <ProvidersPage />
            </TabsContent>
            <TabsContent value="mcp">
              <McpPage />
            </TabsContent>
            <TabsContent value="targets">
              <TargetsPage />
            </TabsContent>
            <TabsContent value="computer-use">
              <ComputerUsePage />
            </TabsContent>
          </>
        )}
      </Tabs>
    </div>
  );
}
