"use client";

import { Badge } from "@/components/ui/badge";

const AVAILABLE_TOOLS = [
  {
    id: "web_search",
    name: "Web Search",
    description: "Search the web for information via SerpAPI",
  },
  {
    id: "document_reader",
    name: "Document Reader",
    description: "Extract text from uploaded PDFs and DOCX files",
  },
  {
    id: "code_executor",
    name: "Code Executor",
    description: "Run Python code in a sandboxed environment",
  },
  {
    id: "data_extractor",
    name: "Data Extractor",
    description: "Extract structured JSON from unstructured text",
  },
  {
    id: "summarizer",
    name: "Summarizer",
    description: "Condense long documents into summaries",
  },
];

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
