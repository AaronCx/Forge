"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { LiveStatusSection } from "@/components/dashboard/sections/LiveStatusSection";
import { UsageCostSection } from "@/components/dashboard/sections/UsageCostSection";
import { RecentRunsSection } from "@/components/dashboard/sections/RecentRunsSection";

export default function DashboardPage() {
  const [connected, setConnected] = useState(false);

  const handleConnectedChange = useCallback((next: boolean) => {
    setConnected(next);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash;
    if (!hash) return;
    // Allow sections to mount before scrolling to the anchor.
    const id = hash.replace(/^#/, "");
    requestAnimationFrame(() => {
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ block: "start" });
    });
  }, []);

  return (
    <div className="space-y-10">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold">Dashboard</h1>
          <p className="mt-1 text-muted-foreground">
            Live status, usage and cost, and recent activity
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div
            className="flex items-center gap-2 text-sm text-muted-foreground"
            title={connected ? "Connected to live stream" : "Disconnected from live stream"}
          >
            <span className="relative flex h-3 w-3" aria-hidden="true">
              <span
                className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  connected ? "animate-ping bg-green-500" : "bg-red-500"
                }`}
              />
              <span
                className={`relative inline-flex h-3 w-3 rounded-full ${
                  connected ? "bg-green-500" : "bg-red-500"
                }`}
              />
            </span>
            <span>{connected ? "Connected" : "Disconnected"}</span>
          </div>
          <Link href="/dashboard/agents/new">
            <Button>Create Agent</Button>
          </Link>
        </div>
      </div>

      <LiveStatusSection onConnectedChange={handleConnectedChange} />
      <UsageCostSection />
      <RecentRunsSection />
    </div>
  );
}
