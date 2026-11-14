/**
 * One list of hypotheses: the `hypotheses` table (pre-registered), the `exploratory` table (stated
 * before computed, after earlier results; its `family` column marks the post-hoc one) and H26 from
 * the `departures` and `departure_tests` tables (post hoc), merged and ordered by the number in
 * each id. Which table a row comes from decides how it is read; the id strings themselves are
 * never relied on.
 */
import {
  type ArtifactCheckRow,
  DataError,
  type ExploratoryRow,
  HYPOTHESIS_ID,
  type HypothesisRow,
  type ReleaseData,
} from "@/lib/data";
import { type Departure, departureFrom, isFinding } from "@/lib/departures";
import { NOT_COMPUTABLE, formatFloat } from "@/lib/format";

export type HypothesisKind = "preregistered" | "exploratory" | "departure";

interface EntryBase {
  id: string;
  number: number;
  /** The headline hypothesis, or a confident outcome: what the analysis holds to be true. */
  heldTrue: boolean;
}

export type HypothesisEntry =
  | (EntryBase & { kind: "preregistered"; row: HypothesisRow; checks: ArtifactCheckRow[] })
  | (EntryBase & { kind: "exploratory"; row: ExploratoryRow })
  | (EntryBase & { kind: "departure"; departure: Departure });

/** When a hypothesis was stated, relative to the analysis. */
export type Timing = "preregistered" | "stated" | "postHoc";

/** The three labels every surface uses (TIMING_* in src/enron_case/report/render.py). */
export const TIMING_LABELS: Record<Timing, string> = {
  preregistered: "pre-registered",
  stated: "stated before computed, after earlier results",
  postHoc: "post hoc",
};

/** What each label means, for the places that spell it out. */
export const TIMING_MEANINGS: Record<Timing, string> = {
  preregistered: "before any real data was analysed",
  stated: "before its own result was computed, but after earlier results were known",
  postHoc: "after every other result was known, still before its own result was computed",
};

/** The `exploratory.family` value of a hypothesis stated after every other result. */
const POST_HOC_FAMILY = "post hoc";

export function timingOf(entry: HypothesisEntry): Timing {
  switch (entry.kind) {
    case "preregistered":
      return "preregistered";
    case "exploratory":
      return entry.row.family === POST_HOC_FAMILY ? "postHoc" : "stated";
    case "departure":
      return "postHoc";
  }
}

/** How many hypotheses carry each timing label. */
export function countByTiming(entries: HypothesisEntry[]): Record<Timing, number> {
  const counts: Record<Timing, number> = { preregistered: 0, stated: 0, postHoc: 0 };
  for (const entry of entries) counts[timingOf(entry)] += 1;
  return counts;
}

/** Within one number, the pre-registered hypotheses come first. */
const KIND_ORDER: Record<HypothesisKind, number> = { preregistered: 0, exploratory: 1, departure: 2 };

function byNumber(a: HypothesisEntry, b: HypothesisEntry): number {
  return a.number - b.number || KIND_ORDER[a.kind] - KIND_ORDER[b.kind] || a.id.localeCompare(b.id);
}

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

/**
 * True when the pre-crisis placebo already shows the crisis change: on the side the crisis median
 * moved to, the placebo interval excludes zero or the placebo median is at least as large. The
 * stated placebo rule still passes such a row when that side is against the prediction or the
 * interval includes zero (placebo_shows_change in src/enron_case/report/render.py).
 */
export function placeboShowsChange(row: ExploratoryRow): boolean {
  const { median_change: median, placebo_median: placebo, placebo_ci_low: low, placebo_ci_high: high } = row;
  if (median === null || placebo === null || low === null || high === null || median === 0) return false;
  const sign = median > 0 ? 1 : -1;
  const excludesZero = sign * low > 0 && sign * high > 0;
  return excludesZero || sign * placebo >= sign * median;
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
  return entries.sort(byNumber);
}

/**
 * Every hypothesis of a release, H26 included. H26 was stated after every other hypothesis, so it
 * is numbered one past their count (config.HYPOTHESES_STATED).
 */
export function releaseHypotheses(data: ReleaseData): HypothesisEntry[] {
  const { hypotheses, exploratory, artifact_checks: checks } = data.tables;
  const others = allHypotheses(hypotheses, exploratory, checks);
  const departure = departureFrom(data, others.length + 1);
  const entry: HypothesisEntry = {
    kind: "departure",
    id: departure.id,
    number: hypothesisNumber(departure.id),
    heldTrue: isFinding(departure),
    departure,
  };
  return [...others, entry].sort(byNumber);
}

/** How many hypotheses of each kind there are: the size of each Holm correction. */
export function countByKind(entries: HypothesisEntry[]): Record<HypothesisKind, number> {
  return {
    preregistered: entries.filter((entry) => entry.kind === "preregistered").length,
    exploratory: entries.filter((entry) => entry.kind === "exploratory").length,
    departure: entries.filter((entry) => entry.kind === "departure").length,
  };
}

/**
 * One line per held-true hypothesis that has a measured change, for the Overview: "Held true: H12
 * — <measure>, change <median> (<interval>), volume-equalised <median> (<interval>)". The headline
 * among the pre-registered hypotheses has its own card and no line here.
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
