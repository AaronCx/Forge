"use client";

import { cn } from "@/lib/utils";
import { X } from "lucide-react";

interface Tab {
  path: string;
  modified: boolean;
}

interface EditorTabsProps {
  tabs: Tab[];
  activeTab: string;
  onSelect: (path: string) => void;
  onClose: (path: string) => void;
}

function getFilename(path: string): string {
  return path.split("/").pop() ?? path;
}

export function EditorTabs({ tabs, activeTab, onSelect, onClose }: EditorTabsProps) {
  if (tabs.length === 0) return null;

  return (
    <div className="flex border-b border-border bg-card overflow-x-auto">
      {tabs.map((tab) => (
        <button
          key={tab.path}
          onClick={() => onSelect(tab.path)}
          className={cn(
            "group flex items-center gap-1.5 border-r border-border px-3 py-1.5 text-xs shrink-0",
            activeTab === tab.path
              ? "bg-background text-foreground"
              : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
          )}
        >
          <span className="truncate max-w-[120px]" title={tab.path}>
            {getFilename(tab.path)}
          </span>
          {tab.modified && (
            <span className="h-1.5 w-1.5 rounded-full bg-blue-400 shrink-0" title="Unsaved changes" />
          )}
          <span
            onClick={(e) => {
              e.stopPropagation();
              onClose(tab.path);
            }}
            className="ml-1 rounded p-0.5 opacity-0 group-hover:opacity-100 hover:bg-accent"
          >
            <X className="h-3 w-3" />
          </span>
        </button>
      ))}
    </div>
  );
}
