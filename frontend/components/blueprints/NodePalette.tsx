"use client";

import { useState } from "react";
import { NodeTypeInfo } from "@/lib/api";

const CATEGORY_ORDER = ["context", "transform", "validate", "agent", "output"];
const CATEGORY_LABELS: Record<string, string> = {
  context: "Context",
  transform: "Transform",
  validate: "Validate",
  agent: "Agent (LLM)",
  output: "Output",
};

interface NodePaletteProps {
  nodeTypes: NodeTypeInfo[];
}

export function NodePalette({ nodeTypes }: NodePaletteProps) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const grouped = CATEGORY_ORDER.map((cat) => ({
    category: cat,
    label: CATEGORY_LABELS[cat] || cat,
    types: nodeTypes.filter((t) => t.category === cat),
  })).filter((g) => g.types.length > 0);

  function onDragStart(event: React.DragEvent, nodeType: NodeTypeInfo) {
    event.dataTransfer.setData("application/blueprint-node", JSON.stringify(nodeType));
    event.dataTransfer.effectAllowed = "move";
  }

  return (
    <div className="w-64 shrink-0 overflow-y-auto border-r border-border bg-card p-3">
      <h3 className="mb-3 text-sm font-semibold text-muted-foreground">Node Palette</h3>
      {grouped.map((group) => (
        <div key={group.category} className="mb-3">
          <button
            onClick={() => setCollapsed((prev) => ({ ...prev, [group.category]: !prev[group.category] }))}
            className="flex w-full items-center justify-between rounded px-2 py-1 text-xs font-medium uppercase tracking-wider text-muted-foreground hover:bg-muted"
          >
            {group.label}
            <span className="text-[10px]">{collapsed[group.category] ? "+" : "−"}</span>
          </button>
          {!collapsed[group.category] && (
            <div className="mt-1 space-y-1">
              {group.types.map((nt) => (
                <div
                  key={nt.key}
                  draggable
                  onDragStart={(e) => onDragStart(e, nt)}
                  className={`cursor-grab rounded-md border p-2 text-xs transition-colors hover:border-primary ${
                    nt.node_class === "agent"
                      ? "border-purple-500/30 bg-purple-500/5"
                      : "border-border bg-muted/50"
                  }`}
                >
                  <div className="font-medium">{nt.display_name}</div>
                  <div className="mt-0.5 text-[10px] text-muted-foreground line-clamp-2">
                    {nt.description}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
