"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { api, Approval } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { isDemoMode } from "@/lib/demo-data";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-500",
  approved: "bg-green-500",
  rejected: "bg-red-500",
};

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"pending" | "all">("pending");
  const [feedbackMap, setFeedbackMap] = useState<Record<string, string>>({});

  useEffect(() => {
    if (isDemoMode()) {
      setApprovals([]);
      setLoading(false);
      return;
    }
    loadApprovals();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  async function loadApprovals() {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      const list = await api.approvals.list(filter, data.session.access_token);
      setApprovals(list);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  async function handleApprove(id: string) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      await api.approvals.approve(id, feedbackMap[id] || "", data.session.access_token);
      await loadApprovals();
    } catch {
      // ignore
    }
  }

  async function handleReject(id: string) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      await api.approvals.reject(id, feedbackMap[id] || "", data.session.access_token);
      await loadApprovals();
    } catch {
      // ignore
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Approvals</h1>
          <p className="mt-1 text-muted-foreground">
            Review and approve pending human-in-the-loop checkpoints
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant={filter === "pending" ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter("pending")}
          >
            Pending
          </Button>
          <Button
            variant={filter === "all" ? "default" : "outline"}
            size="sm"
            onClick={() => setFilter("all")}
          >
            All
          </Button>
        </div>
      </div>

      <div className="mt-6 space-y-4">
        {loading ? (
          <div className="space-y-3">
            {[1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-lg bg-muted" />)}
          </div>
        ) : approvals.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {filter === "pending"
              ? "No pending approvals. Blueprint execution will pause here when an approval gate is reached."
              : "No approvals found."}
          </p>
        ) : (
          approvals.map((approval) => (
            <Card key={approval.id}>
              <CardContent className="py-4">
                <div className="flex items-start gap-3">
                  <div
                    className={`mt-1 h-3 w-3 rounded-full ${STATUS_COLORS[approval.status] || "bg-gray-500"}`}
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{approval.status}</Badge>
                      <span className="text-xs text-muted-foreground font-mono">
                        Node: {approval.node_id}
                      </span>
                      <span className="text-xs text-muted-foreground font-mono">
                        Run: {approval.blueprint_run_id.slice(0, 8)}
                      </span>
                    </div>
                    {approval.context && (
                      <div className="mt-2 rounded bg-muted p-3 text-sm">
                        <p className="font-medium">
                          {String((approval.context as Record<string, unknown>).message || "Review required")}
                        </p>
                        {(approval.context as Record<string, unknown>).upstream_data ? (
                          <pre className="mt-1 text-xs text-muted-foreground overflow-auto max-h-32">
                            {JSON.stringify((approval.context as Record<string, unknown>).upstream_data, null, 2)}
                          </pre>
                        ) : null}
                      </div>
                    )}
                    {approval.status === "pending" && (
                      <div className="mt-3 flex items-center gap-2">
                        <Input
                          placeholder="Optional feedback..."
                          className="max-w-xs"
                          value={feedbackMap[approval.id] || ""}
                          onChange={(e) => setFeedbackMap({ ...feedbackMap, [approval.id]: e.target.value })}
                        />
                        <Button size="sm" onClick={() => handleApprove(approval.id)}>
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => handleReject(approval.id)}
                        >
                          Reject
                        </Button>
                      </div>
                    )}
                    {approval.feedback && (
                      <p className="mt-2 text-sm text-muted-foreground">
                        Feedback: {approval.feedback}
                      </p>
                    )}
                    <p className="mt-1 text-xs text-muted-foreground">
                      {new Date(approval.created_at).toLocaleString()}
                      {approval.decided_at && (
                        <> &middot; Decided: {new Date(approval.decided_at).toLocaleString()}</>
                      )}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
