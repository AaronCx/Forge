"use client";

import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { useCallback } from "react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { SuitesView } from "./SuitesView";
import ComparePage from "../compare/page";

/**
 * PR-4 Evals — Suites + Compare under one workspace home.
 *
 * Compare keeps living at /dashboard/compare as a deep-link target; this page
 * just hosts it as a tab. Tab persistence via ?tab=suites|compare.
 */
const TABS = ["suites", "compare"] as const;
type EvalsTab = (typeof TABS)[number];

export default function EvalsPage() {
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

  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Evals</h1>
        <p className="text-sm text-muted-foreground">
          Eval suites and side-by-side model comparison.
        </p>
      </header>

      <Tabs value={tab} onValueChange={onChange}>
        <TabsList>
          <TabsTrigger value="suites">Suites</TabsTrigger>
          <TabsTrigger value="compare">Compare</TabsTrigger>
        </TabsList>

        <TabsContent value="suites">
          <SuitesView />
        </TabsContent>
        <TabsContent value="compare">
          <ComparePage />
        </TabsContent>
      </Tabs>
    </div>
  );
}
