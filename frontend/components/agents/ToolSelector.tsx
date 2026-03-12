"use client";

import { Badge } from "@/components/ui/badge";
import { AVAILABLE_TOOLS } from "@/lib/constants";

interface ToolSelectorProps {
  selected: string[];
  onChange: (tools: string[]) => void;
}

export function ToolSelector({ selected, onChange }: ToolSelectorProps) {
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
    </div>
  );
}
