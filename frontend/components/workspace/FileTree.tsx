"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import {
  ChevronRight,
  ChevronDown,
  File,
  FileCode,
  FileJson,
  FileText,
  Folder,
  FolderOpen,
} from "lucide-react";

interface FileEntry {
  name: string;
  path: string;
  type: "file" | "directory";
  size: number | null;
  children: FileEntry[] | null;
}

interface FileTreeProps {
  files: FileEntry[];
  selectedPath: string;
  onSelect: (path: string) => void;
  highlightedPaths?: Set<string>;
}

function getFileIcon(name: string) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const codeExts = new Set(["js", "jsx", "ts", "tsx", "py", "rb", "go", "rs", "java", "c", "cpp", "h", "sh", "bash"]);
  const jsonExts = new Set(["json", "toml", "yaml", "yml"]);

  if (codeExts.has(ext)) return <FileCode className="h-4 w-4 text-blue-400" />;
  if (jsonExts.has(ext)) return <FileJson className="h-4 w-4 text-yellow-400" />;
  if (ext === "md" || ext === "txt" || ext === "rst") return <FileText className="h-4 w-4 text-gray-400" />;
  return <File className="h-4 w-4 text-gray-500" />;
}

function TreeNode({
  entry,
  depth,
  selectedPath,
  onSelect,
  highlightedPaths,
}: {
  entry: FileEntry;
  depth: number;
  selectedPath: string;
  onSelect: (path: string) => void;
  highlightedPaths?: Set<string>;
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  const isSelected = selectedPath === entry.path;
  const isHighlighted = highlightedPaths?.has(entry.path);

  if (entry.type === "directory") {
    return (
      <div>
        <button
          onClick={() => setExpanded(!expanded)}
          className={cn(
            "flex w-full items-center gap-1 rounded px-1 py-0.5 text-sm hover:bg-accent",
            isHighlighted && "bg-yellow-900/30"
          )}
          style={{ paddingLeft: `${depth * 12 + 4}px` }}
        >
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          )}
          {expanded ? (
            <FolderOpen className="h-4 w-4 shrink-0 text-amber-400" />
          ) : (
            <Folder className="h-4 w-4 shrink-0 text-amber-400" />
          )}
          <span className="truncate">{entry.name}</span>
        </button>
        {expanded && entry.children && (
          <div>
            {entry.children.map((child) => (
              <TreeNode
                key={child.path}
                entry={child}
                depth={depth + 1}
                selectedPath={selectedPath}
                onSelect={onSelect}
                highlightedPaths={highlightedPaths}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <button
      onClick={() => onSelect(entry.path)}
      className={cn(
        "flex w-full items-center gap-1 rounded px-1 py-0.5 text-sm hover:bg-accent",
        isSelected && "bg-accent text-accent-foreground",
        isHighlighted && !isSelected && "bg-yellow-900/30"
      )}
      style={{ paddingLeft: `${depth * 12 + 20}px` }}
    >
      {getFileIcon(entry.name)}
      <span className="truncate">{entry.name}</span>
    </button>
  );
}

export function FileTree({ files, selectedPath, onSelect, highlightedPaths }: FileTreeProps) {
  return (
    <div className="py-1">
      {files.map((entry) => (
        <TreeNode
          key={entry.path}
          entry={entry}
          depth={0}
          selectedPath={selectedPath}
          onSelect={onSelect}
          highlightedPaths={highlightedPaths}
        />
      ))}
      {files.length === 0 && (
        <p className="px-4 py-8 text-center text-sm text-muted-foreground">
          No files yet. Create one to get started.
        </p>
      )}
    </div>
  );
}
