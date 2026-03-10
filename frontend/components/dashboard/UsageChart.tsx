"use client";

interface UsageChartProps {
  totalTokens: number;
}

export function UsageChart({ totalTokens }: UsageChartProps) {
  // Estimate cost at $0.15 per 1M input tokens (gpt-4o-mini)
  const estimatedCost = (totalTokens / 1_000_000) * 0.15;

  return (
    <div className="rounded-lg border border-border p-6">
      <h3 className="text-sm font-medium text-muted-foreground">
        Estimated Cost
      </h3>
      <p className="mt-2 text-3xl font-bold">${estimatedCost.toFixed(4)}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Based on {totalTokens.toLocaleString()} tokens at gpt-4o-mini rates
      </p>
    </div>
  );
}
