/**
 * How the UI names and explains the release's `other` bucket. The release keeps the label `other`
 * (contract stability); on screen it is "Outside the <baseline> groups": internal people with no
 * tie in the baseline period plus communities under k. It is not a
 * community, so it is described by its size and by how much mail involves it, never as a group.
 * Every number here comes from community_groups and community_graph.
 */
import type { CommunityEdgeRow, CommunityGroupRow, Period } from "@/lib/data";
import { formatNumber, formatShare } from "@/lib/format";
import { OTHER_GROUP, type TieMeasure } from "@/lib/network";

/** Short form where space is tight (chord labels, tie rows). */
export const OUTSIDE_SHORT = "outside";

const YEAR_LENGTH = 4;

/** The baseline as a name: its year when it is one calendar year, else null. */
function baselineYear(baseline: Period | null): string | null {
  if (baseline === null) return null;
  const year = baseline.start.slice(0, YEAR_LENGTH);
  return baseline.end.slice(0, YEAR_LENGTH) === year ? year : null;
}

/** "the 2000 groups", or "the baseline groups" when the baseline is not one calendar year. */
function baselineGroups(baseline: Period | null): string {
  return `the ${baselineYear(baseline) ?? "baseline"} groups`;
}

export function outsideLabel(baseline: Period | null): string {
  return `Outside ${baselineGroups(baseline)}`;
}

/** A group label as shown: the outside label for the bucket, the release label otherwise. */
export function displayGroup(group: string, baseline: Period | null): string {
  return group === OTHER_GROUP ? outsideLabel(baseline) : group;
}

/** The bucket's size from community_groups; null when the release does not publish it. */
export function outsidePeople(groups: CommunityGroupRow[]): number | null {
  return groups.find((g) => g.group === OTHER_GROUP)?.n_persons ?? null;
}

/**
 * Who is in the bucket, in one sentence, from the data only: the release says how many they are
 * and why they have no group, not when or whether they appear in the network.
 */
export function outsideExplanation(people: number, minGroupSize: number, baseline: Period | null): string {
  const year = baselineYear(baseline);
  const period = year ?? "the baseline period";
  const group = year === null ? "baseline group" : `${year} group`;
  return (
    `${formatNumber(people)} internal people without a ${group}: no tie in ${period}, ` +
    `or in groups under ${minGroupSize} people; not a community.`
  );
}

function touchesOutside(edge: CommunityEdgeRow): boolean {
  return edge.src_group === OTHER_GROUP || edge.dst_group === OTHER_GROUP;
}

/**
 * The one rule for the outside share: over the rows of the weeks kept, the measure on rows with
 * the bucket at either end over the measure on all rows (suppressed counts as 0); null when
 * nothing is published there.
 */
export function outsideShare(
  edges: CommunityEdgeRow[],
  measure: TieMeasure,
  keepWeek: (week: string) => boolean,
): number | null {
  let total = 0;
  let outside = 0;
  for (const edge of edges) {
    if (!keepWeek(edge.week)) continue;
    const value = edge[measure] ?? 0;
    total += value;
    if (touchesOutside(edge)) outside += value;
  }
  return total > 0 ? outside / total : null;
}

/**
 * The Network caption's share: `n_messages` in one week. `n_messages` counts per sender–recipient
 * pair, so this is a share of pair counts, not of distinct messages.
 */
export function outsideWeekShare(edges: CommunityEdgeRow[], week: string | null): number | null {
  return outsideShare(edges, "n_messages", (candidate) => candidate === week);
}

export function outsideWeekCaption(share: number | null, baseline: Period | null): string {
  if (share === null) return "No mail between people was published for this week.";
  return (
    `${formatShare(share)} of this week's mail (counted per sender–recipient pair) involves people ` +
    `outside ${baselineGroups(baseline)}.`
  );
}

/** A period's share of weight involving outside people, for the Clusters view. */
export function outsidePeriodCaption(share: number, baseline: Period | null): string {
  return `${formatShare(share)} of this period's weight involves people outside ${baselineGroups(baseline)}.`;
}

export interface OutsideTies {
  /** The week's weight between the bucket and real groups, both directions; suppressed as 0. */
  weight: number;
  /** How many real groups had a published tie with the bucket that week. */
  groups: number;
}

/** The week's ties between the bucket and the real groups, summed into one line. */
export function outsideTies(edges: CommunityEdgeRow[], week: string | null): OutsideTies {
  const partners = new Set<string>();
  let weight = 0;
  for (const edge of edges) {
    if (edge.week !== week || !touchesOutside(edge) || edge.src_group === edge.dst_group) continue;
    partners.add(edge.src_group === OTHER_GROUP ? edge.dst_group : edge.src_group);
    weight += edge.weight ?? 0;
  }
  return { weight, groups: partners.size };
}
