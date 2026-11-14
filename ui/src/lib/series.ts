import type { HypothesisRow, Period, ReleaseData, Scope, WeeklyMetricRow } from "@/lib/data";

export const DEFAULT_VARIANT = "default";

export interface SeriesPoint {
  week: string;
  /** null where the release suppressed the cell: drawn as a gap, never as zero. */
  value: number | null;
}

export interface SeriesSelection {
  metric: string;
  scope: Scope;
  variant: string;
}

export function variants(rows: WeeklyMetricRow[]): string[] {
  const all = [...new Set(rows.map((row) => row.variant))].sort();
  return all.includes(DEFAULT_VARIANT) ? [DEFAULT_VARIANT, ...all.filter((v) => v !== DEFAULT_VARIANT)] : all;
}

export function metricSeries(rows: WeeklyMetricRow[], selection: SeriesSelection): SeriesPoint[] {
  return rows
    .filter(
      (row) =>
        row.metric === selection.metric && row.scope === selection.scope && row.variant === selection.variant,
    )
    .map((row) => ({ week: row.week, value: row.value }))
    .sort((a, b) => a.week.localeCompare(b.week));
}

/** The pre-registered hypothesis that tests this metric in this scope, if any. */
export function hypothesisFor(
  hypotheses: HypothesisRow[],
  metric: string,
  scope: Scope,
): HypothesisRow | undefined {
  return hypotheses.find((row) => row.metric === metric && row.scope === scope);
}

export function headline(hypotheses: HypothesisRow[]): HypothesisRow | undefined {
  return hypotheses.find((row) => row.is_headline && row.supported === "yes");
}

export function baselinePeriod(data: ReleaseData): Period | null {
  const { baseline_start: start, baseline_end: end } = data.run.parameters;
  return typeof start === "string" && typeof end === "string" ? { start, end } : null;
}

/** Monday-based weeks covered by the metric series, in order. */
export function analysisWeeks(rows: WeeklyMetricRow[]): string[] {
  return [...new Set(rows.map((row) => row.week))].sort();
}

/** The first series week on or after an ISO date (markers snap onto the weekly axis). */
export function snapToWeek(weeks: string[], date: string): string | null {
  for (let i = 0; i < weeks.length; i += 1) {
    const week = weeks[i];
    const next = weeks[i + 1];
    if (week !== undefined && week <= date && (next === undefined || date < next)) return week;
  }
  return null;
}
