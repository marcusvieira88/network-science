import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation } from "d3-force";
import type { SimulationLinkDatum, SimulationNodeDatum } from "d3-force";

import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";

export const OTHER_GROUP = "other";
const LAYOUT_TICKS = 300;
const MIN_RADIUS = 10;
const RADIUS_PER_SQRT_PERSON = 4;
const CHART_SLOTS = 8;
/** In the Individuals mode a group's disc fades to a membrane around its anonymous points. */
export const MEMBRANE_OPACITY = 0.25;
/** Height of the WebGL network canvas and of its loading placeholder, in pixels. */
export const NETWORK_HEIGHT = 460;

export interface PlacedGroup {
  group: string;
  nPersons: number;
  x: number;
  y: number;
  radius: number;
}

export interface GroupTie {
  a: string;
  b: string;
  /** Weight in each direction; suppressed cells count as 0. */
  weightAB: number;
  weightBA: number;
  total: number;
}

export interface WeekGraph {
  ties: GroupTie[];
  /** Within-group weight per group for this week. */
  internal: Record<string, number>;
}

export function groupRadius(nPersons: number): number {
  return MIN_RADIUS + RADIUS_PER_SQRT_PERSON * Math.sqrt(nPersons);
}

function pairKey(a: string, b: string): [string, string] {
  return a < b ? [a, b] : [b, a];
}

/** Ties between distinct groups, summed per unordered pair; suppressed weights count as 0. */
export function weekGraph(edges: CommunityEdgeRow[], week: string | null): WeekGraph {
  const ties = new Map<string, GroupTie>();
  const internal: Record<string, number> = {};
  for (const edge of edges) {
    if (week !== null && edge.week !== week) continue;
    const weight = edge.weight ?? 0;
    if (edge.src_group === edge.dst_group) {
      internal[edge.src_group] = (internal[edge.src_group] ?? 0) + weight;
      continue;
    }
    const [a, b] = pairKey(edge.src_group, edge.dst_group);
    const key = `${a}\u0000${b}`;
    const tie = ties.get(key) ?? { a, b, weightAB: 0, weightBA: 0, total: 0 };
    if (edge.src_group === a) tie.weightAB += weight;
    else tie.weightBA += weight;
    tie.total += weight;
    ties.set(key, tie);
  }
  return {
    ties: [...ties.values()].sort((x, y) => y.total - x.total || x.a.localeCompare(y.a) || x.b.localeCompare(y.b)),
    internal,
  };
}

/** The heaviest tie between two groups in any of the weeks: one scale for every week. */
export function maxWeeklyTie(edges: CommunityEdgeRow[], weeks: string[]): number {
  return Math.max(1, ...weeks.map((week) => weekGraph(edges, week).ties[0]?.total ?? 0));
}

interface LayoutNode extends SimulationNodeDatum {
  group: string;
  nPersons: number;
  radius: number;
}

type LayoutLink = SimulationLinkDatum<LayoutNode> & { strength: number };

/**
 * One force layout over the ties of all weeks, computed once so that groups stay in place while
 * the week changes. d3-force's initial placement and jitter are deterministic, so the same data
 * gives the same picture.
 */
/** Ties in one week (or all weeks when `week` is null) between published groups only. */
export function publishedTies(edges: CommunityEdgeRow[], week: string | null, groupIds: Iterable<string>): WeekGraph["ties"] {
  const known = new Set(groupIds);
  return weekGraph(edges, week).ties.filter((tie) => known.has(tie.a) && known.has(tie.b));
}

export function layoutGroups(
  groups: CommunityGroupRow[],
  edges: CommunityEdgeRow[],
  width: number,
  height: number,
): PlacedGroup[] {
  const nodes: LayoutNode[] = [...groups]
    .sort((x, y) => x.group.localeCompare(y.group))
    .map((g) => ({ group: g.group, nPersons: g.n_persons, radius: groupRadius(g.n_persons) }));
  const all = publishedTies(edges, null, nodes.map((n) => n.group));
  const maxTotal = Math.max(1, ...all.map((t) => t.total));
  const links: LayoutLink[] = all.map((t) => ({
    source: t.a,
    target: t.b,
    strength: t.total / maxTotal,
  }));
  const minSide = Math.min(width, height);
  const simulation = forceSimulation(nodes)
    .force(
      "link",
      forceLink<LayoutNode, LayoutLink>(links)
        .id((n) => n.group)
        .distance(minSide / 3)
        .strength((link) => 0.05 + 0.5 * link.strength),
    )
    .force("charge", forceManyBody().strength(-minSide))
    .force("collide", forceCollide<LayoutNode>((n) => n.radius + 12))
    .force("center", forceCenter(width / 2, height / 2))
    .stop();
  simulation.tick(LAYOUT_TICKS);
  return nodes.map((n) => ({
    group: n.group,
    nPersons: n.nPersons,
    radius: n.radius,
    x: clamp(n.x ?? width / 2, n.radius, width - n.radius),
    y: clamp(n.y ?? height / 2, n.radius, height - n.radius),
  }));
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), high);
}

/** Label order with `other` last: the order groups are listed and coloured in. */
export function compareGroups(a: string, b: string): number {
  if (a === OTHER_GROUP || b === OTHER_GROUP) return Number(a === OTHER_GROUP) - Number(b === OTHER_GROUP);
  return a.localeCompare(b);
}

/** Fixed colour slot per group by label order; `other` is neutral. Colour follows the group. */
export function groupColor(group: string, orderedGroups: string[]): string {
  if (group === OTHER_GROUP) return "var(--chart-other)";
  const named = orderedGroups.filter((g) => g !== OTHER_GROUP);
  const slot = named.indexOf(group);
  return slot >= 0 && slot < CHART_SLOTS ? `var(--chart-${slot + 1})` : "var(--chart-other)";
}
