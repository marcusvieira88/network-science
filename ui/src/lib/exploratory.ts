import type { ExploratoryRow } from "@/lib/data";
import { NOT_COMPUTABLE, formatFloat } from "@/lib/format";

/** "median (low to high)"; the interval part is a dash when a bound could not be computed. */
export function formatEstimate(median: number | null, low: number | null, high: number | null): string {
  if (median === null) return NOT_COMPUTABLE;
  const interval = low === null || high === null ? NOT_COMPUTABLE : `${formatFloat(low)} to ${formatFloat(high)}`;
  return `${formatFloat(median)} (${interval})`;
}

export function equalisedEstimate(row: ExploratoryRow): string {
  return formatEstimate(row.equalised_median, row.equalised_ci_low, row.equalised_ci_high);
}

export function hasEqualisedResult(row: ExploratoryRow): boolean {
  return row.equalised_median !== null;
}

export function byOrder(rows: ExploratoryRow[]): ExploratoryRow[] {
  return [...rows].sort((a, b) => a.order - b.order);
}

/** One sentence per confident exploratory hypothesis, for the Overview. */
export function exploratoryLeads(rows: ExploratoryRow[]): string[] {
  return byOrder(rows)
    .filter((row) => row.outcome === "confident")
    .map((row) => `Exploratory: ${row.measure} — ${row.outcome}, volume-equalised change ${equalisedEstimate(row)}`);
}
