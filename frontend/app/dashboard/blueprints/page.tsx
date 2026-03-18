"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { api, Blueprint } from "@/lib/api";
import { isDemoMode } from "@/lib/demo-data";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

function BlueprintCard({ blueprint }: { blueprint: Blueprint }) {
  const demo = isDemoMode();
  const href = demo
    ? `/dashboard/blueprints/${blueprint.id}`
    : `/dashboard/blueprints/${blueprint.id}/edit`;

  return (
    <Link href={href}>
      <Card className="h-full transition-colors hover:border-primary/50">
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between">
            <CardTitle className="text-base">{blueprint.name}</CardTitle>
            <Badge variant="outline" className="text-[10px]">
              v{blueprint.version}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground line-clamp-2">
            {blueprint.description}
          </p>
          <div className="mt-3 flex flex-wrap gap-1">
            {blueprint.nodes.slice(0, 4).map((node) => (
              <span
                key={node.id}
                className={`rounded px-1.5 py-0.5 text-[10px] ${
                  node.type.startsWith("llm_")
                    ? "bg-purple-500/10 text-purple-400"
                    : "bg-blue-500/10 text-blue-400"
                }`}
              >
                {node.label || node.type}
              </span>
            ))}
            {blueprint.nodes.length > 4 && (
              <span className="text-[10px] text-muted-foreground">
                +{blueprint.nodes.length - 4} more
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

export default function BlueprintsPage() {
  const [blueprints, setBlueprints] = useState<Blueprint[]>([]);
  const [templates, setTemplates] = useState<Blueprint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const router = useRouter();

  useEffect(() => {
    if (isDemoMode()) {
      api.blueprints.templates().then(setTemplates).catch(() => {});
      setLoading(false);
      return;
    }
    async function load() {
      const { data } = await supabase.auth.getSession();
      if (!data.session) return;

      try {
        const [userBps, templateBps] = await Promise.all([
          api.blueprints.list(data.session.access_token),
          api.blueprints.templates(),
        ]);
        setBlueprints(userBps);
        setTemplates(templateBps);
      } catch {
        setError("Failed to load blueprints. Check your connection.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function handleUseTemplate(template: Blueprint) {
    if (isDemoMode()) return;
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;

    try {
      const bp = await api.blueprints.create(
        {
          name: `${template.name} (copy)`,
          description: template.description,
          nodes: template.nodes,
          context_config: template.context_config,
          tool_scope: template.tool_scope,
          retry_policy: template.retry_policy,
        },
        data.session.access_token,
      );
      router.push(`/dashboard/blueprints/${bp.id}/edit`);
    } catch {
      // Handle error silently
    }
  }

  return (
    <div>
      {error && (
        <div className="mb-4 rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Blueprints</h1>
          <p className="mt-1 text-muted-foreground">
            Visual DAG workflows with deterministic and AI-powered nodes
          </p>
        </div>
        {!isDemoMode() && (
          <Link href="/dashboard/blueprints/new">
            <Button>New Blueprint</Button>
          </Link>
        )}
      </div>

      {loading ? (
        <p className="mt-8 text-muted-foreground">Loading blueprints...</p>
      ) : (
        <>
          {blueprints.length > 0 && (
            <div className="mt-8">
              <h2 className="text-xl font-semibold">Your Blueprints</h2>
              <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                {blueprints.map((bp) => (
                  <BlueprintCard key={bp.id} blueprint={bp} />
                ))}
              </div>
            </div>
          )}

          {templates.length > 0 && (
            <div className="mt-8">
              <h2 className="text-xl font-semibold">Templates</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Pre-built workflows ready to customize
              </p>
              <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                {templates.map((bp) => (
                  <Card key={bp.id} className="h-full">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">{bp.name}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-sm text-muted-foreground line-clamp-2">
                        {bp.description}
                      </p>
                      <div className="mt-3 flex flex-wrap gap-1">
                        {bp.nodes.slice(0, 4).map((node) => (
                          <span
                            key={node.id}
                            className={`rounded px-1.5 py-0.5 text-[10px] ${
                              node.type.startsWith("llm_")
                                ? "bg-purple-500/10 text-purple-400"
                                : "bg-blue-500/10 text-blue-400"
                            }`}
                          >
                            {node.label || node.type}
                          </span>
                        ))}
                      </div>
                      {!isDemoMode() && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="mt-3"
                          onClick={() => handleUseTemplate(bp)}
                        >
                          Use Template
                        </Button>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {blueprints.length === 0 && templates.length === 0 && (
            <div className="mt-8 rounded-lg border border-dashed border-border p-12 text-center">
              <h3 className="text-lg font-semibold">No blueprints yet</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Create your first blueprint to build visual workflows.
              </p>
              {!isDemoMode() && (
                <Link href="/dashboard/blueprints/new">
                  <Button className="mt-4">New Blueprint</Button>
                </Link>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
