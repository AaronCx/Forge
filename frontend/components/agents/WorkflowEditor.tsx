"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface WorkflowEditorProps {
  steps: string[];
  onChange: (steps: string[]) => void;
}

export function WorkflowEditor({ steps, onChange }: WorkflowEditorProps) {
  function addStep() {
    onChange([...steps, ""]);
  }

  function removeStep(index: number) {
    onChange(steps.filter((_, i) => i !== index));
  }

  function updateStep(index: number, value: string) {
    const newSteps = [...steps];
    newSteps[index] = value;
    onChange(newSteps);
  }

  function moveStep(index: number, direction: "up" | "down") {
    const newSteps = [...steps];
    const targetIndex = direction === "up" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= newSteps.length) return;
    [newSteps[index], newSteps[targetIndex]] = [newSteps[targetIndex], newSteps[index]];
    onChange(newSteps);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <label className="text-sm font-medium">Workflow Steps</label>
          <p className="text-xs text-muted-foreground">
            Define the sequence of instructions the agent will follow.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={addStep}>
          Add Step
        </Button>
      </div>

      {steps.length === 0 && (
        <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          No workflow steps defined. The agent will process input in a single step.
        </p>
      )}

      <div className="space-y-2">
        {steps.map((step, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium">
              {i + 1}
            </span>
            <Input
              value={step}
              onChange={(e) => updateStep(i, e.target.value)}
              placeholder={`Step ${i + 1}: e.g., "Extract all dates and amounts"`}
              className="flex-1"
            />
            <div className="flex gap-1">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => moveStep(i, "up")}
                disabled={i === 0}
                className="h-8 w-8 p-0"
              >
                ↑
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => moveStep(i, "down")}
                disabled={i === steps.length - 1}
                className="h-8 w-8 p-0"
              >
                ↓
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => removeStep(i)}
                className="h-8 w-8 p-0 text-destructive hover:text-destructive"
              >
                ×
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
