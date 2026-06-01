"use client";

import { Suspense, useCallback } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import PromptsPage from "../prompts/page";
import KnowledgePage from "../knowledge/page";

/**
 * PR-4 Studio Library — Prompts + Knowledge as tabs. The existing standalone
 * /dashboard/prompts and /dashboard/knowledge routes stay live as deep-link
 * destinations; this page just hosts the two views under one workspace home.
 *
 * Tab persistence: ?tab=prompts | ?tab=knowledge so refreshes and bookmarks
 * land on the right pane. useSearchParams must run inside a Suspense boundary
 * so Next.js can statically generate the surrounding shell.
 */
export default function LibraryPage() {
  return (
    <Suspense fallback={<LibraryShell tab="prompts" />}>
      <LibraryContent />
    </Suspense>
  );
}

function LibraryContent() {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const tab = params?.get("tab") === "knowledge" ? "knowledge" : "prompts";

  const onChange = useCallback(
    (next: string) => {
      const url = new URL(window.location.href);
      url.searchParams.set("tab", next);
      router.replace(`${pathname}?${url.searchParams.toString()}`, { scroll: false });
    },
    [pathname, router],
  );

  return <LibraryShell tab={tab} onChange={onChange} interactive />;
}

function LibraryShell({
  tab,
  onChange,
  interactive,
}: {
  tab: "prompts" | "knowledge";
  onChange?: (next: string) => void;
  interactive?: boolean;
}) {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Library</h1>
        <p className="text-sm text-muted-foreground">
          Prompts and knowledge collections — attachable to any agent in Studio.
        </p>
      </header>

      <Tabs value={tab} onValueChange={onChange ?? (() => {})}>
        <TabsList>
          <TabsTrigger value="prompts">Prompts</TabsTrigger>
          <TabsTrigger value="knowledge">Knowledge</TabsTrigger>
        </TabsList>

        {interactive && (
          <>
            <TabsContent value="prompts">
              <PromptsPage />
            </TabsContent>
            <TabsContent value="knowledge">
              <KnowledgePage />
            </TabsContent>
          </>
        )}
      </Tabs>
    </div>
  );
}
