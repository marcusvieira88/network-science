const DECIMALS = 2;

export function formatNumber(value: number | null, decimals: number = DECIMALS): string {
  if (value === null) return "suppressed";
  return value.toLocaleString("en-US", { maximumFractionDigits: decimals, minimumFractionDigits: 0 });
}

export function formatShare(value: number | null): string {
  if (value === null) return "n/a";
  return `${(value * 100).toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
}

export function formatP(value: number): string {
  return value < 0.001 ? "< 0.001" : value.toFixed(3);
}

export function formatInterval(low: number, high: number): string {
  return `[${formatNumber(low)}, ${formatNumber(high)}]`;
}

export const METRIC_LABELS: Record<string, string> = {
  volume: "Message volume",
  active_persons: "Active persons",
  density: "Density",
  reciprocity: "Reciprocity",
  indegree_gini: "In-degree concentration (Gini)",
  cross_community_share: "Cross-group share",
  external_share: "External share",
  tie_turnover: "Tie turnover",
};

export function metricLabel(metric: string): string {
  return METRIC_LABELS[metric] ?? metric;
}
