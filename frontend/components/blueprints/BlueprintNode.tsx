"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

interface BlueprintNodeData {
  label: string;
  nodeType: string;
  nodeClass: string;
  config: Record<string, unknown>;
  status?: "pending" | "running" | "done" | "error";
  tokens?: number;
  duration?: number;
  [key: string]: unknown;
}

function BlueprintNodeComponent({ data, selected }: NodeProps) {
  const d = data as BlueprintNodeData;
  const isAgent = d.nodeClass === "agent";
  const status = d.status || "pending";

  const statusColors: Record<string, string> = {
    pending: "border-border",
    running: "border-blue-500 shadow-blue-500/20 shadow-lg",
    done: "border-green-500",
    error: "border-red-500",
  };

  const headerBg = isAgent ? "bg-purple-500/10" : "bg-muted";
  const borderColor = status !== "pending" ? statusColors[status] : isAgent ? "border-purple-500/40" : "border-border";

  return (
    <div
      className={`min-w-[180px] rounded-lg border-2 bg-card text-xs ${borderColor} ${
        selected ? "ring-2 ring-primary" : ""
      } ${status === "running" ? "animate-pulse" : ""}`}
    >
      <Handle type="target" position={Position.Top} className="!bg-muted-foreground" />

      <div className={`rounded-t-md px-3 py-1.5 ${headerBg}`}>
        <div className="flex items-center justify-between gap-2">
          <span className="font-semibold">{d.label || d.nodeType}</span>
          <span
            className={`rounded px-1 py-0.5 text-[9px] font-medium ${
              isAgent ? "bg-purple-500/20 text-purple-300" : "bg-blue-500/20 text-blue-300"
            }`}
          >
            {isAgent ? "AGT" : "DET"}
          </span>
        </div>
      </div>

      <div className="px-3 py-2">
        <div className="text-[10px] text-muted-foreground">{d.nodeType}</div>
        {status === "running" && d.tokens !== undefined && d.tokens > 0 && (
          <div className="mt-1 text-[10px] text-blue-400">{d.tokens.toLocaleString()} tokens</div>
        )}
        {status === "done" && d.duration !== undefined && (
          <div className="mt-1 text-[10px] text-green-400">{(d.duration / 1000).toFixed(1)}s</div>
        )}
        {status === "error" && (
          <div className="mt-1 text-[10px] text-red-400">Failed</div>
        )}
      </div>

      <Handle type="source" position={Position.Bottom} className="!bg-muted-foreground" />
    </div>
  );
}

export const BlueprintNodeComponent_Memo = memo(BlueprintNodeComponent);
