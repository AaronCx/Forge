"use client";

import { Suspense, useCallback } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { SuitesView } from "./SuitesView";
import ComparePage from "../compare/page";

const TABS = ["suites", "compare"] as const;
type EvalsTab = (typeof TABS)[number];

export default function EvalsPage() {
  return (
    <Suspense fallback={<EvalsShell tab="suites" />}>
      <EvalsContent />
    </Suspense>
  );
}

function EvalsContent() {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const raw = params?.get("tab") ?? "suites";
  const tab: EvalsTab = (TABS as readonly string[]).includes(raw)
    ? (raw as EvalsTab)
    : "suites";

  const onChange = useCallback(
    (next: string) => {
      const url = new URL(window.location.href);
      url.searchParams.set("tab", next);
      router.replace(`${pathname}?${url.searchParams.toString()}`, { scroll: false });
    },
    [pathname, router],
  );

  return <EvalsShell tab={tab} onChange={onChange} interactive />;
}

function EvalsShell({
  tab,
  onChange,
  interactive,
}: {
  tab: EvalsTab;
  onChange?: (next: string) => void;
  interactive?: boolean;
}) {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Evals</h1>
        <p className="text-sm text-muted-foreground">
          Eval suites and side-by-side model comparison.
        </p>
      </header>

      <Tabs value={tab} onValueChange={onChange ?? (() => {})}>
        <TabsList>
          <TabsTrigger value="suites">Suites</TabsTrigger>
          <TabsTrigger value="compare">Compare</TabsTrigger>
        </TabsList>

        {interactive && (
          <>
            <TabsContent value="suites">
              <SuitesView />
            </TabsContent>
            <TabsContent value="compare">
              <ComparePage />
            </TabsContent>
          </>
        )}
      </Tabs>
    </div>
  );
}
