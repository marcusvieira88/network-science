/**
 * Data shaping for the Clusters view: message weight between the published groups, summed over a
 * period. Inputs are only `community_groups` and `community_graph`, so nothing finer than a group
 * of at least k people can appear.
 */
import { type CommunityEdgeRow, type CommunityGroupRow, DataError, type Period } from "@/lib/data";
import { OTHER_GROUP } from "@/lib/network";

export const PERIOD_OPTIONS = [
  { id: "baseline", label: "Baseline year" },
  { id: "crisis", label: "Crisis weeks" },
  { id: "all", label: "All weeks" },
] as const;

export type PeriodId = (typeof PERIOD_OPTIONS)[number]["id"];

export const TOP_PARTNERS = 3;

export interface ClusterPeriods {
  baseline: Period;
  crisis: Period;
}

/** The date range of a period option; null for all weeks. */
export function periodRange(id: PeriodId, periods: ClusterPeriods): Period | null {
  return id === "all" ? null : periods[id];
}

/** A week belongs to a period when its Monday falls inside it, as in finding/hypotheses.py. */
export function weekInPeriod(week: string, range: Period | null): boolean {
  return range === null || (range.start <= week && week <= range.end);
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

function groupOrder(a: string, b: string): number {
  if (a === OTHER_GROUP || b === OTHER_GROUP) return Number(a === OTHER_GROUP) - Number(b === OTHER_GROUP);
  return a.localeCompare(b);
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
  const sorted = [...groupRows].sort((x, y) => groupOrder(x.group, y.group));
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
  /** The heaviest partner groups (both directions summed), at most TOP_PARTNERS. */
  partners: Partner[];
}

export function groupSummaries(matrix: ClusterMatrix): GroupSummary[] {
  return matrix.groups.map((group, i) => {
    const row = matrix.symmetric[i] ?? [];
    const total = row.reduce((sum, weight) => sum + weight, 0);
    const within = row[i] ?? 0;
    const partners = matrix.groups
      .map((other, j) => ({ group: other, weight: row[j] ?? 0 }))
      .filter((p, j) => j !== i && p.weight > 0)
      .sort((x, y) => y.weight - x.weight || groupOrder(x.group, y.group))
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

export interface ShareChange {
  group: string;
  /** Cross-group share (1 − within-group share) in each period. */
  before: number;
  after: number;
  change: number;
}

/** The group whose cross-group share changed most (either way); null if none is comparable. */
export function largestCrossShareChange(before: GroupSummary[], after: GroupSummary[]): ShareChange | null {
  const later = new Map(after.map((s) => [s.group, s.withinShare]));
  let largest: ShareChange | null = null;
  for (const summary of before) {
    const withinAfter = later.get(summary.group);
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
