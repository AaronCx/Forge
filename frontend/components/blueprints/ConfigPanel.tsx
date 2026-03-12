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

        {/* Steer node config */}
        {(type === "steer_see" || type === "steer_ocr" || type === "steer_focus") && (
          <div>
            <Label className="text-xs">Target App</Label>
            <Input
              value={(config.target as string) || (config.app as string) || "screen"}
              onChange={(e) => updateConfig(type === "steer_focus" ? "app" : "target", e.target.value)}
              placeholder="App name or 'screen'"
              className="mt-1"
            />
          </div>
        )}

        {type === "steer_click" && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">X</Label>
                <Input
                  type="number"
                  value={(config.x as number) || 0}
                  onChange={(e) => updateConfig("x", parseInt(e.target.value))}
                  className="mt-1"
                />
              </div>
              <div>
                <Label className="text-xs">Y</Label>
                <Input
                  type="number"
                  value={(config.y as number) || 0}
                  onChange={(e) => updateConfig("y", parseInt(e.target.value))}
                  className="mt-1"
                />
              </div>
            </div>
            <div>
              <Label className="text-xs">Or Element Text</Label>
              <Input
                value={(config.element_text as string) || ""}
                onChange={(e) => updateConfig("element_text", e.target.value)}
                placeholder="Click on this text"
                className="mt-1"
              />
            </div>
          </>
        )}

        {type === "steer_type" && (
          <div>
            <Label className="text-xs">Text to Type</Label>
            <Textarea
              value={(config.text as string) || ""}
              onChange={(e) => updateConfig("text", e.target.value)}
              className="mt-1"
              rows={3}
            />
          </div>
        )}

        {type === "steer_hotkey" && (
          <div>
            <Label className="text-xs">Key Combination</Label>
            <Input
              value={(config.keys as string) || ""}
              onChange={(e) => updateConfig("keys", e.target.value)}
              placeholder="cmd+s, cmd+tab, cmd+shift+p"
              className="mt-1"
            />
          </div>
        )}

        {type === "steer_scroll" && (
          <>
            <div>
              <Label className="text-xs">Direction</Label>
              <select
                value={(config.direction as string) || "down"}
                onChange={(e) => updateConfig("direction", e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              >
                <option value="up">Up</option>
                <option value="down">Down</option>
                <option value="left">Left</option>
                <option value="right">Right</option>
              </select>
            </div>
            <div>
              <Label className="text-xs">Amount</Label>
              <Input
                type="number"
                value={(config.amount as number) || 3}
                onChange={(e) => updateConfig("amount", parseInt(e.target.value))}
                className="mt-1"
              />
            </div>
          </>
        )}

        {type === "steer_find" && (
          <div>
            <Label className="text-xs">Search Text</Label>
            <Input
              value={(config.search_text as string) || ""}
              onChange={(e) => updateConfig("search_text", e.target.value)}
              placeholder="Text or element to find"
              className="mt-1"
            />
          </div>
        )}

        {type === "steer_wait" && (
          <>
            <div>
              <Label className="text-xs">Wait For Text</Label>
              <Input
                value={(config.search_text as string) || ""}
                onChange={(e) => updateConfig("search_text", e.target.value)}
                placeholder="Text to wait for"
                className="mt-1"
              />
            </div>
            <div>
              <Label className="text-xs">Timeout (seconds)</Label>
              <Input
                type="number"
                value={(config.timeout as number) || 10}
                onChange={(e) => updateConfig("timeout", parseInt(e.target.value))}
                className="mt-1"
              />
            </div>
          </>
        )}

        {type === "steer_clipboard" && (
          <div>
            <Label className="text-xs">Action</Label>
            <select
              value={(config.action as string) || "read"}
              onChange={(e) => updateConfig("action", e.target.value)}
              className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
            >
              <option value="read">Read</option>
              <option value="write">Write</option>
            </select>
          </div>
        )}

        {/* Drive node config */}
        {type === "drive_session" && (
          <>
            <div>
              <Label className="text-xs">Action</Label>
              <select
                value={(config.action as string) || "create"}
                onChange={(e) => updateConfig("action", e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              >
                <option value="create">Create</option>
                <option value="list">List</option>
                <option value="kill">Kill</option>
              </select>
            </div>
            <div>
              <Label className="text-xs">Session Name</Label>
              <Input
                value={(config.session as string) || ""}
                onChange={(e) => updateConfig("session", e.target.value)}
                placeholder="Auto-generated if empty"
                className="mt-1"
              />
            </div>
          </>
        )}

        {type === "drive_run" && (
          <>
            <div>
              <Label className="text-xs">Command</Label>
              <Input
                value={(config.command as string) || ""}
                onChange={(e) => updateConfig("command", e.target.value)}
                placeholder="ls -la, npm test, etc."
                className="mt-1 font-mono text-xs"
              />
            </div>
            <div>
              <Label className="text-xs">Session</Label>
              <Input
                value={(config.session as string) || ""}
                onChange={(e) => updateConfig("session", e.target.value)}
                className="mt-1"
              />
            </div>
            <div>
              <Label className="text-xs">Timeout (seconds)</Label>
              <Input
                type="number"
                value={(config.timeout as number) || 30}
                onChange={(e) => updateConfig("timeout", parseInt(e.target.value))}
                className="mt-1"
              />
            </div>
          </>
        )}

        {type === "drive_fanout" && (
          <div>
            <Label className="text-xs">Commands (one per line)</Label>
            <Textarea
              value={Array.isArray(config.commands) ? (config.commands as string[]).join("\n") : ""}
              onChange={(e) => updateConfig("commands", e.target.value.split("\n").filter(Boolean))}
              placeholder="npm test&#10;npm run lint&#10;npm run build"
              className="mt-1 font-mono text-xs"
              rows={4}
            />
          </div>
        )}

        {(type === "drive_logs" || type === "drive_send" || type === "drive_poll") && (
          <div>
            <Label className="text-xs">Session</Label>
            <Input
              value={(config.session as string) || ""}
              onChange={(e) => updateConfig("session", e.target.value)}
              className="mt-1"
            />
          </div>
        )}

        {/* CU Agent node config */}
        {(type === "cu_planner" || type === "cu_verifier") && (
          <div>
            <Label className="text-xs">Objective</Label>
            <Textarea
              value={(config.objective as string) || ""}
              onChange={(e) => updateConfig("objective", e.target.value)}
              placeholder="What should the agent accomplish?"
              className="mt-1"
              rows={3}
            />
          </div>
        )}

        {type === "cu_analyzer" && (
          <div>
            <Label className="text-xs">Focus</Label>
            <Input
              value={(config.focus as string) || ""}
              onChange={(e) => updateConfig("focus", e.target.value)}
              placeholder="What to focus the analysis on"
              className="mt-1"
            />
          </div>
        )}

        {/* Agent Control node config */}
        {type === "agent_spawn" && (
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Agent Backend</Label>
              <select
                value={(config.backend as string) || "claude-code"}
                onChange={(e) => updateConfig("backend", e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              >
                <option value="claude-code">Claude Code</option>
                <option value="codex-cli">Codex CLI</option>
                <option value="gemini-cli">Gemini CLI</option>
                <option value="aider">Aider</option>
                <option value="custom">Custom</option>
              </select>
            </div>
            <div>
              <Label className="text-xs">Working Directory</Label>
              <Input
                value={(config.working_directory as string) || ""}
                onChange={(e) => updateConfig("working_directory", e.target.value)}
                placeholder="/path/to/project"
                className="mt-1"
              />
            </div>
          </div>
        )}
        {(type === "agent_prompt") && (
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Session</Label>
              <Input
                value={(config.session as string) || ""}
                onChange={(e) => updateConfig("session", e.target.value)}
                placeholder="Session name (from agent_spawn)"
                className="mt-1"
              />
            </div>
            <div>
              <Label className="text-xs">Prompt</Label>
              <Textarea
                value={(config.prompt as string) || ""}
                onChange={(e) => updateConfig("prompt", e.target.value)}
                placeholder="Task prompt to send to the agent"
                className="mt-1"
                rows={4}
              />
            </div>
          </div>
        )}
        {(type === "agent_monitor" || type === "agent_stop") && (
          <div>
            <Label className="text-xs">Session</Label>
            <Input
              value={(config.session as string) || ""}
              onChange={(e) => updateConfig("session", e.target.value)}
              placeholder="Session name"
              className="mt-1"
            />
          </div>
        )}
        {type === "agent_wait" && (
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Session</Label>
              <Input
                value={(config.session as string) || ""}
                onChange={(e) => updateConfig("session", e.target.value)}
                placeholder="Session name"
                className="mt-1"
              />
            </div>
            <div>
              <Label className="text-xs">Timeout (seconds)</Label>
              <Input
                type="number"
                value={(config.timeout as number) || 300}
                onChange={(e) => updateConfig("timeout", parseInt(e.target.value) || 300)}
                className="mt-1"
              />
            </div>
            <div>
              <Label className="text-xs">Completion Pattern (optional regex)</Label>
              <Input
                value={(config.completion_pattern as string) || ""}
                onChange={(e) => updateConfig("completion_pattern", e.target.value)}
                placeholder="e.g. >\s*$"
                className="mt-1"
              />
            </div>
          </div>
        )}
        {type === "agent_result" && (
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Session</Label>
              <Input
                value={(config.session as string) || ""}
                onChange={(e) => updateConfig("session", e.target.value)}
                placeholder="Session name"
                className="mt-1"
              />
            </div>
            <div>
              <Label className="text-xs">Output Format</Label>
              <select
                value={(config.output_format as string) || "text"}
                onChange={(e) => updateConfig("output_format", e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              >
                <option value="text">Text</option>
                <option value="json">JSON</option>
                <option value="diff">Diff</option>
              </select>
            </div>
          </div>
        )}
        {type === "recording_control" && (
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Action</Label>
              <select
                value={(config.action as string) || "start"}
                onChange={(e) => updateConfig("action", e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              >
                <option value="start">Start Recording</option>
                <option value="stop">Stop Recording</option>
              </select>
            </div>
            <div>
              <Label className="text-xs">Quality</Label>
              <select
                value={(config.quality as string) || "medium"}
                onChange={(e) => updateConfig("quality", e.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              >
                <option value="low">Low (720p 15fps)</option>
                <option value="medium">Medium (1080p 30fps)</option>
                <option value="high">High (native 30fps)</option>
              </select>
            </div>
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
