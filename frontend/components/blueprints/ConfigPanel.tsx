"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ModelSelector } from "@/components/ModelSelector";
import { Textarea } from "@/components/ui/textarea";


interface ConfigPanelProps {
  selectedNode: {
    id: string;
    type: string;
    label: string;
    nodeClass: string;
    config: Record<string, unknown>;
  } | null;
  blueprintName: string;
  blueprintDescription: string;
  onBlueprintNameChange: (name: string) => void;
  onBlueprintDescriptionChange: (desc: string) => void;
  onNodeConfigChange: (nodeId: string, config: Record<string, unknown>) => void;
  onNodeLabelChange: (nodeId: string, label: string) => void;
}

export function ConfigPanel({
  selectedNode,
  blueprintName,
  blueprintDescription,
  onBlueprintNameChange,
  onBlueprintDescriptionChange,
  onNodeConfigChange,
  onNodeLabelChange,
}: ConfigPanelProps) {
  if (!selectedNode) {
    return (
      <div className="w-72 shrink-0 overflow-y-auto border-l border-border bg-card p-4">
        <h3 className="mb-4 text-sm font-semibold">Blueprint Settings</h3>
        <div className="space-y-3">
          <div>
            <Label htmlFor="bp-name" className="text-xs">Name</Label>
            <Input
              id="bp-name"
              value={blueprintName}
              onChange={(e) => onBlueprintNameChange(e.target.value)}
              className="mt-1"
            />
          </div>
          <div>
            <Label htmlFor="bp-desc" className="text-xs">Description</Label>
            <Textarea
              id="bp-desc"
              value={blueprintDescription}
              onChange={(e) => onBlueprintDescriptionChange(e.target.value)}
              className="mt-1"
              rows={3}
            />
          </div>
        </div>
        <p className="mt-6 text-xs text-muted-foreground">
          Select a node on the canvas to configure it.
        </p>
      </div>
    );
  }

  const { id, type, label, nodeClass, config } = selectedNode;

  function updateConfig(key: string, value: unknown) {
    onNodeConfigChange(id, { ...config, [key]: value });
  }

  return (
    <div className="w-72 shrink-0 overflow-y-auto border-l border-border bg-card p-4">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold">Node Config</h3>
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
            nodeClass === "agent" ? "bg-purple-500/20 text-purple-300" : "bg-blue-500/20 text-blue-300"
          }`}
        >
          {type}
        </span>
      </div>

      <div className="space-y-3">
        <div>
          <Label className="text-xs">Label</Label>
          <Input
            value={label}
            onChange={(e) => onNodeLabelChange(id, e.target.value)}
            className="mt-1"
          />
        </div>

        {/* Type-specific config */}
        {(type === "fetch_url") && (
          <div>
            <Label className="text-xs">URL</Label>
            <Input
              value={(config.url as string) || ""}
              onChange={(e) => updateConfig("url", e.target.value)}
              placeholder="https://..."
              className="mt-1"
            />
          </div>
        )}

        {type === "text_splitter" && (
          <>
            <div>
              <Label className="text-xs">Chunk Size</Label>
              <Input
                type="number"
                value={(config.chunk_size as number) || 2000}
                onChange={(e) => updateConfig("chunk_size", parseInt(e.target.value))}
                className="mt-1"
              />
            </div>
            <div>
              <Label className="text-xs">Overlap</Label>
              <Input
                type="number"
                value={(config.overlap as number) || 200}
                onChange={(e) => updateConfig("overlap", parseInt(e.target.value))}
                className="mt-1"
              />
            </div>
          </>
        )}

        {type === "template_renderer" && (
          <div>
            <Label className="text-xs">Template</Label>
            <Textarea
              value={(config.template as string) || ""}
              onChange={(e) => updateConfig("template", e.target.value)}
              placeholder="Use {{variable}} for substitution"
              className="mt-1"
              rows={4}
            />
          </div>
        )}

        {type === "json_validator" && (
          <div>
            <Label className="text-xs">JSON Schema</Label>
            <Textarea
              value={typeof config.schema === "object" ? JSON.stringify(config.schema, null, 2) : ""}
              onChange={(e) => {
                try { updateConfig("schema", JSON.parse(e.target.value)); } catch { /* ignore */ }
              }}
              className="mt-1 font-mono text-xs"
              rows={4}
            />
          </div>
        )}

        {type === "output_formatter" && (
          <div>
            <Label className="text-xs">Format</Label>
            <select
              value={(config.format as string) || "markdown"}
              onChange={(e) => updateConfig("format", e.target.value)}
              className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            >
              <option value="json">JSON</option>
              <option value="markdown">Markdown</option>
              <option value="plain">Plain Text</option>
            </select>
          </div>
        )}

        {type === "webhook" && (
          <div>
            <Label className="text-xs">Webhook URL</Label>
            <Input
              value={(config.url as string) || ""}
              onChange={(e) => updateConfig("url", e.target.value)}
              placeholder="https://..."
              className="mt-1"
            />
          </div>
        )}

        {/* Agent node config */}
        {nodeClass === "agent" && (
          <>
            <div>
              <Label className="text-xs">System Prompt</Label>
              <Textarea
                value={(config.system_prompt as string) || ""}
                onChange={(e) => updateConfig("system_prompt", e.target.value)}
                className="mt-1"
                rows={4}
              />
            </div>
            <ModelSelector
              value={(config.model as string) || null}
              onChange={(m) => updateConfig("model", m)}
              label="Model Override"
            />
            {type === "llm_summarize" && (
              <div>
                <Label className="text-xs">Summary Length</Label>
                <select
                  value={(config.max_length as string) || "medium"}
                  onChange={(e) => updateConfig("max_length", e.target.value)}
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                >
                  <option value="short">Short</option>
                  <option value="medium">Medium</option>
                  <option value="long">Long</option>
                </select>
              </div>
            )}
            {type === "llm_review" && (
              <div>
                <Label className="text-xs">Review Type</Label>
                <select
                  value={(config.review_type as string) || "code"}
                  onChange={(e) => updateConfig("review_type", e.target.value)}
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                >
                  <option value="code">Code Review</option>
                  <option value="text">Text Review</option>
                  <option value="security">Security Review</option>
                </select>
              </div>
            )}
            {type === "llm_implement" && (
              <div>
                <Label className="text-xs">Language</Label>
                <Input
                  value={(config.language as string) || "python"}
                  onChange={(e) => updateConfig("language", e.target.value)}
                  className="mt-1"
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
