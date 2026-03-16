"use client";

interface UsageChartProps {
  totalTokens: number;
}

export function UsageChart({ totalTokens }: UsageChartProps) {
  return (
    <div className="rounded-lg border border-border p-6">
      <h3 className="text-sm font-medium text-muted-foreground">
        Token Usage
      </h3>
      <p className="mt-2 text-3xl font-bold">
        ~{totalTokens.toLocaleString()}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        total tokens used
      </p>
      <p className="mt-2 text-xs text-muted-foreground">
        Check the Analytics page for per-model cost breakdowns.
      </p>
    </div>
  );
}
