/**
 * Data shaping for the Clusters view: message weight between the published groups, summed over a
 * period. Inputs are only `community_groups` and `community_graph`, so nothing finer than a group
 * of at least k people can appear.
 */
import { type ArtifactCheckRow, type CommunityEdgeRow, type CommunityGroupRow, DataError, type Period } from "@/lib/data";
import { OTHER_GROUP, compareGroups } from "@/lib/network";

export const PERIOD_OPTIONS = [
  { id: "baseline", label: "Baseline year" },
  { id: "crisis", label: "Crisis weeks" },
  { id: "all", label: "All weeks" },
] as const;

export type PeriodId = (typeof PERIOD_OPTIONS)[number]["id"];

export const TOP_PARTNERS = 3;

/** The H2 artifact check for drift of groups fixed on the baseline (finding/artifacts.py). */
export const DRIFT_CHECK = { hypothesis: "H2", check: "baseline_placebo" } as const;

/** Whether the release's drift check passed; null when it could not run or is absent. */
export function driftCheckPasses(checks: ArtifactCheckRow[]): boolean | null {
  const row = checks.find((c) => c.hypothesis === DRIFT_CHECK.hypothesis && c.check === DRIFT_CHECK.check);
  return row?.passes ?? null;
}

export interface ClusterPeriods {
  baseline: Period;
  crisis: Period;
}

/** The date range of a period option; null for all weeks. */
export function periodRange(id: PeriodId, periods: ClusterPeriods): Period | null {
  return id === "all" ? null : periods[id];
}

const DAYS_AFTER_MONDAY = 6;

/** The Sunday ending the week that starts on this Monday (ISO dates). */
export function weekEnd(monday: string): string {
  const day = new Date(`${monday}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() + DAYS_AFTER_MONDAY);
  return day.toISOString().slice(0, 10);
}

/**
 * A week belongs to a period when any of its days falls inside it, so the week of an event that
 * starts a window midweek (the crisis begins on a Tuesday) is counted.
 */
export function weekInPeriod(week: string, range: Period | null): boolean {
  return range === null || (week <= range.end && weekEnd(week) >= range.start);
}

/** The weeks with at least one published tie in the period, in order. */
export function periodWeeks(edges: CommunityEdgeRow[], range: Period | null): string[] {
  return [...new Set(edges.filter((e) => weekInPeriod(e.week, range)).map((e) => e.week))].sort();
}

export interface ClusterMatrix {
  /** Group labels by label order, `other` last; the index of every row and column. */
  groups: string[];
  sizes: number[];
  /** directed[i][j]: weight sent from group i to group j; suppressed cells count as 0. */
  directed: number[][];
  /** Both directions summed between two groups; the diagonal holds the within-group weight once. */
  symmetric: number[][];
}

function requireIndex(index: Map<string, number>, group: string): number {
  const found = index.get(group);
  if (found === undefined) throw new DataError(`community_graph has a tie to unpublished group ${group}`);
  return found;
}

export function clusterMatrix(
  groupRows: CommunityGroupRow[],
  edges: CommunityEdgeRow[],
  range: Period | null,
): ClusterMatrix {
  const sorted = [...groupRows].sort((x, y) => compareGroups(x.group, y.group));
  const groups = sorted.map((g) => g.group);
  const index = new Map(groups.map((group, i) => [group, i]));
  const directed = groups.map(() => groups.map(() => 0));
  for (const edge of edges) {
    if (!weekInPeriod(edge.week, range)) continue;
    const src = requireIndex(index, edge.src_group);
    const dst = requireIndex(index, edge.dst_group);
    const row = directed[src];
    if (row) row[dst] = (row[dst] ?? 0) + (edge.weight ?? 0);
  }
  const cell = (i: number, j: number) => directed[i]?.[j] ?? 0;
  const symmetric = groups.map((_, i) => groups.map((__, j) => (i === j ? cell(i, i) : cell(i, j) + cell(j, i))));
  return { groups, sizes: sorted.map((g) => g.n_persons), directed, symmetric };
}

export interface Partner {
  group: string;
  weight: number;
}

export interface GroupSummary {
  group: string;
  nPersons: number;
  /** All weight the group takes part in: within the group, sent and received. */
  total: number;
  within: number;
  /** within / total; null when the group has no weight in the period. */
  withinShare: number | null;
  /** The heaviest partner groups (both directions summed), at most TOP_PARTNERS; never the outside bucket. */
  partners: Partner[];
}

export function groupSummaries(matrix: ClusterMatrix): GroupSummary[] {
  return matrix.groups.map((group, i) => {
    const row = matrix.symmetric[i] ?? [];
    const total = row.reduce((sum, weight) => sum + weight, 0);
    const within = row[i] ?? 0;
    // The outside bucket is no partner group, and it has none: it is not a community.
    const partners = (group === OTHER_GROUP ? [] : matrix.groups)
      .map((partner, j) => ({ group: partner, weight: row[j] ?? 0 }))
      .filter((p, j) => j !== i && p.weight > 0 && p.group !== OTHER_GROUP)
      .sort((x, y) => y.weight - x.weight || compareGroups(x.group, y.group))
      .slice(0, TOP_PARTNERS);
    return {
      group,
      nPersons: matrix.sizes[i] ?? 0,
      total,
      within,
      withinShare: total > 0 ? within / total : null,
      partners,
    };
  });
}

/**
 * The period's weight with the outside bucket at either end over all its weight (each directed
 * cell once); null when the period has no weight or the release has no bucket.
 */
export function outsideWeightShare(matrix: ClusterMatrix): number | null {
  const outside = matrix.groups.indexOf(OTHER_GROUP);
  if (outside < 0) return null;
  let total = 0;
  let involving = 0;
  matrix.directed.forEach((row, i) =>
    row.forEach((weight, j) => {
      total += weight;
      if (i === outside || j === outside) involving += weight;
    }),
  );
  return total > 0 ? involving / total : null;
}

export interface ShareChange {
  group: string;
  /** Cross-group share (1 − within-group share) in each period. */
  before: number;
  after: number;
  change: number;
}

/**
 * The named group whose cross-group share changed most (either way); null if none is comparable.
 * `other` is skipped: it is not a community but the people with no tie in the baseline period
 * (mostly people who first appear later) plus communities under k, so its share describes no group.
 */
export function largestCrossShareChange(before: GroupSummary[], after: GroupSummary[]): ShareChange | null {
  const later = new Map(after.map((s) => [s.group, s.withinShare]));
  let largest: ShareChange | null = null;
  for (const summary of before) {
    const withinAfter = later.get(summary.group);
    if (summary.group === OTHER_GROUP) continue;
    if (summary.withinShare === null || withinAfter === null || withinAfter === undefined) continue;
    const candidate = {
      group: summary.group,
      before: 1 - summary.withinShare,
      after: 1 - withinAfter,
      change: summary.withinShare - withinAfter,
    };
    if (largest === null || Math.abs(candidate.change) > Math.abs(largest.change)) largest = candidate;
  }
  return largest;
}
