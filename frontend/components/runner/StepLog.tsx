"use client";

interface StepLogEntry {
  type: string;
  data: string | { step: number; result: string; duration_ms?: number };
}

interface StepLogProps {
  logs: StepLogEntry[];
}

export function StepLog({ logs }: StepLogProps) {
  if (logs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Step execution log will appear here...
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {logs.map((log, i) => (
        <div
          key={i}
          className="flex items-start gap-3 rounded-lg border border-border p-3"
        >
          <div
            className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${
              log.type === "error"
                ? "bg-destructive"
                : log.type === "done"
                  ? "bg-green-500"
                  : "bg-primary"
            }`}
          />
          <div className="min-w-0 flex-1">
            <p className="text-sm">
              {typeof log.data === "string"
                ? log.data
                : log.data.result || `Step ${log.data.step}`}
            </p>
            {typeof log.data === "object" && log.data.duration_ms && (
              <p className="mt-0.5 text-xs text-muted-foreground">
                {log.data.duration_ms}ms
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
