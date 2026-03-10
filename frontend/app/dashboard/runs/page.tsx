"use client";

import { RunHistory } from "@/components/dashboard/RunHistory";

export default function RunsPage() {
  return (
    <div>
      <h1 className="text-3xl font-bold">Run History</h1>
      <p className="mt-1 text-muted-foreground">
        View all your agent execution results
      </p>
      <div className="mt-6">
        <RunHistory />
      </div>
    </div>
  );
}
