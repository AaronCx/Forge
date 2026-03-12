"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { api, MCPTool } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { AVAILABLE_TOOLS } from "@/lib/constants";
import { isDemoMode } from "@/lib/demo-data";

interface ToolSelectorProps {
  selected: string[];
  onChange: (tools: string[]) => void;
}

export function ToolSelector({ selected, onChange }: ToolSelectorProps) {
  const [mcpTools, setMcpTools] = useState<MCPTool[]>([]);

  useEffect(() => {
    if (isDemoMode()) return;
    loadMcpTools();
  }, []);

  async function loadMcpTools() {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;
    try {
      const tools = await api.mcp.tools(data.session.access_token);
      // Filter out built-in tools (already in AVAILABLE_TOOLS)
      setMcpTools(tools.filter((t) => t.source !== "built-in"));
    } catch {
      // API may not be running
    }
  }

  function toggle(toolId: string) {
    if (selected.includes(toolId)) {
      onChange(selected.filter((t) => t !== toolId));
    } else {
      onChange([...selected, toolId]);
    }
  }

  return (
    <div className="space-y-3">
      <label className="text-sm font-medium">Tools</label>
      <p className="text-xs text-muted-foreground">
        Select the tools your agent can use during execution.
      </p>

      {/* Built-in tools */}
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
        Built-in
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {AVAILABLE_TOOLS.map((tool) => {
          const isSelected = selected.includes(tool.id);
          return (
            <button
              key={tool.id}
              type="button"
              onClick={() => toggle(tool.id)}
              className={`flex flex-col items-start rounded-lg border p-4 text-left transition-colors ${
                isSelected
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-muted-foreground/30"
              }`}
            >
              <div className="flex w-full items-center justify-between">
                <span className="text-sm font-medium">{tool.name}</span>
                {isSelected && <Badge variant="default">Active</Badge>}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {tool.description}
              </p>
            </button>
          );
        })}
      </div>

      {/* MCP tools */}
      {mcpTools.length > 0 && (
        <>
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider pt-2">
            MCP Tools
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {mcpTools.map((tool) => {
              const toolId = `${tool.source_id}:${tool.name}`;
              const isSelected = selected.includes(toolId);
              return (
                <button
                  key={toolId}
                  type="button"
                  onClick={() => toggle(toolId)}
                  className={`flex flex-col items-start rounded-lg border p-4 text-left transition-colors ${
                    isSelected
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-muted-foreground/30"
                  }`}
                >
                  <div className="flex w-full items-center justify-between">
                    <span className="text-sm font-medium">{tool.display_name}</span>
                    <div className="flex gap-1">
                      <Badge variant="secondary" className="text-xs">
                        {tool.source}
                      </Badge>
                      {isSelected && <Badge variant="default">Active</Badge>}
                    </div>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {tool.description}
                  </p>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
