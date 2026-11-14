/**
 * One list of hypotheses: the `hypotheses` table (stated before any data) and the `exploratory`
 * table (stated before being computed) merged and ordered by the number in each id. Which table a
 * row comes from decides how it is read; the id strings themselves are never relied on.
 */
import { type ArtifactCheckRow, DataError, type ExploratoryRow, HYPOTHESIS_ID, type HypothesisRow } from "@/lib/data";
import { NOT_COMPUTABLE, formatFloat } from "@/lib/format";

export type HypothesisKind = "preregistered" | "exploratory";

interface EntryBase {
  id: string;
  number: number;
  /** The headline hypothesis, or a confident outcome: what the analysis holds to be true. */
  heldTrue: boolean;
}

export type HypothesisEntry =
  | (EntryBase & { kind: "preregistered"; row: HypothesisRow; checks: ArtifactCheckRow[] })
  | (EntryBase & { kind: "exploratory"; row: ExploratoryRow });

/** When each kind of hypothesis was stated, relative to the analysis. */
export const STATED: Record<HypothesisKind, string> = {
  preregistered: "before any data",
  exploratory: "before being computed",
};

/** Within one number, the hypotheses stated before any data come first. */
const KIND_ORDER: Record<HypothesisKind, number> = { preregistered: 0, exploratory: 1 };

/** The number at the end of an id ("H12" → 12); parseRelease already refuses an id without one. */
export function hypothesisNumber(id: string): number {
  const match = HYPOTHESIS_ID.exec(id);
  if (!match?.[1]) throw new DataError(`hypothesis id "${id}" has no number`);
  return Number(match[1]);
}

/** "median (low to high)"; the interval part is a dash when a bound could not be computed. */
export function formatEstimate(median: number | null, low: number | null, high: number | null): string {
  if (median === null) return NOT_COMPUTABLE;
  const interval = low === null || high === null ? NOT_COMPUTABLE : `${formatFloat(low)} to ${formatFloat(high)}`;
  return `${formatFloat(median)} (${interval})`;
}

/** The retention check's result ("passes"/"fails" with its estimate), or null where none ran. */
export function retentionCheck(row: ExploratoryRow): string | null {
  if (row.retention_passes === null) return null;
  const verdict = row.retention_passes ? "passes" : "fails";
  return `${verdict}, ${formatEstimate(row.retention_median, row.retention_ci_low, row.retention_ci_high)}`;
}

/** The volume-equalised result, or null where none was computed. */
export function equalisedEstimate(row: ExploratoryRow): string | null {
  if (row.equalised_median === null) return null;
  return formatEstimate(row.equalised_median, row.equalised_ci_low, row.equalised_ci_high);
}

export function allHypotheses(
  hypotheses: HypothesisRow[],
  exploratory: ExploratoryRow[],
  checks: ArtifactCheckRow[],
): HypothesisEntry[] {
  const entries: HypothesisEntry[] = [
    ...hypotheses.map((row) => ({
      kind: "preregistered" as const,
      id: row.hypothesis,
      number: hypothesisNumber(row.hypothesis),
      heldTrue: row.is_headline,
      row,
      checks: checks.filter((check) => check.hypothesis === row.hypothesis),
    })),
    ...exploratory.map((row) => ({
      kind: "exploratory" as const,
      id: row.hypothesis,
      number: hypothesisNumber(row.hypothesis),
      heldTrue: row.outcome === "confident",
      row,
    })),
  ];
  return entries.sort(
    (a, b) => a.number - b.number || KIND_ORDER[a.kind] - KIND_ORDER[b.kind] || a.id.localeCompare(b.id),
  );
}

/** How many hypotheses of each kind there are: the size of each Holm correction. */
export function countByKind(entries: HypothesisEntry[]): Record<HypothesisKind, number> {
  return {
    preregistered: entries.filter((entry) => entry.kind === "preregistered").length,
    exploratory: entries.filter((entry) => entry.kind === "exploratory").length,
  };
}

/**
 * One line per held-true hypothesis that has a measured change, for the Overview: "Held true: H12
 * — <measure>, change <median> (<interval>), volume-equalised <median> (<interval>)". The headline
 * among the hypotheses stated before any data has its own card and no line here.
 */
export function heldTrueLines(entries: HypothesisEntry[]): string[] {
  return entries.flatMap((entry) => {
    if (entry.kind !== "exploratory" || !entry.heldTrue) return [];
    const { row } = entry;
    const equalised = equalisedEstimate(row);
    const change = formatEstimate(row.median_change, row.ci_low, row.ci_high);
    return [`Held true: ${entry.id} — ${row.measure}, change ${change}${equalised ? `, volume-equalised ${equalised}` : ""}`];
  });
}
