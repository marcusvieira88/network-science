/**
 * Pure mapping for the network's Overlap mode: the week's heaviest ties between two published
 * groups are drawn as intersecting contours instead of lines, and the group positions are relaxed so
 * each such pair overlaps by its depth while every other pair stays apart.
 *
 * An overlap means mail between two groups, never shared members: each person is in exactly one
 * group. Everything here is a group-level published count; nothing is drawn per person.
 */
import type { CommunityEdgeRow } from "@/lib/data";
import { type GroupTie, publishedTies, weekGraph } from "@/lib/network";
import type { Position } from "@/lib/sigmaNetwork";

/** The week's heaviest pairs by message count drawn as overlaps; the other ties stay lines. */
export const OVERLAP_PAIRS = 6;
/** Deepest overlap drawn, as a share of the smaller diameter: the smaller disc is never swallowed. */
export const OVERLAP_MAX_DEPTH = 0.8;
/** Fixed number of passes over every pair of groups in the distance-constraint solve. */
export const OVERLAP_ITERATIONS = 200;
/**
 * Closing passes that only push apart, so every pair that does not overlap ends at least the
 * global layout's smallest gap apart even where overlaps pull against each other.
 */
export const SEPARATION_PASSES = 100;
/**
 * In the Overlap mode the contour layer (lib/overlapContours.ts) draws each group; Sigma's disc is
 * invisible and stays only for hover, search and the label. Transparent *black*: Sigma blends
 * colours as if premultiplied, so a "#rrggbb00" disc would still add its colour.
 */
export const OVERLAP_DISC_COLOR = "#00000000";

/** A pair of published groups drawn as overlapping discs this week. */
export interface Overlap {
  a: string;
  b: string;
  /** Messages between the two groups this week, both directions. */
  messages: number;
  /** The pair's message weight this week, as the Groups mode would draw its line. */
  weight: number;
  /** Shared messages / (the group's own within-group messages + shared messages), per side. */
  shareA: number;
  shareB: number;
  /** The drawn depth: the larger side share, capped at OVERLAP_MAX_DEPTH. */
  depth: number;
}

export interface WeekOverlaps {
  overlaps: Overlap[];
  /** The week's other published ties, drawn as ordinary lines (by weight, as in the Groups mode). */
  lines: GroupTie[];
}

/** A pair whose centres the solver pulls to `targetDistance` of their radii and depth. */
export interface OverlapPair {
  a: string;
  b: string;
  depth: number;
}

function clampUnit(value: number): number {
  return Math.min(Math.max(value, 0), 1);
}

/** Shared messages as a share of one side's own within-group messages plus the shared ones. */
export function sideShare(shared: number, own: number): number {
  const total = own + shared;
  return total > 0 ? clampUnit(shared / total) : 0;
}

/**
 * The pair's depth: the share of the side with fewer own messages (the larger of the two side
 * shares), capped so the smaller disc always shows its far edge.
 */
export function overlapDepth(shared: number, ownA: number, ownB: number): number {
  return Math.min(sideShare(shared, Math.min(ownA, ownB)), OVERLAP_MAX_DEPTH);
}

/** Centre distance for a pair: depth 0 touches, depth 1 would reach the smaller disc's far side. */
export function targetDistance(radiusA: number, radiusB: number, depth: number): number {
  return radiusA + radiusB - depth * 2 * Math.min(radiusA, radiusB);
}

/** One key per unordered pair, in the order weekGraph names a tie (a < b). */
function pairId(a: string, b: string): string {
  return a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`;
}

function weightOf(weights: ReadonlyMap<string, GroupTie>, tie: GroupTie): number {
  const weighted = weights.get(pairId(tie.a, tie.b));
  if (!weighted) throw new Error(`no weight for the tie ${tie.a}-${tie.b}`);
  return weighted.total;
}

/**
 * The week's overlaps and remaining lines between published groups. The outside bucket never takes
 * part and suppressed counts are 0, exactly as in `publishedTies`; a pair with no published
 * message is never an overlap.
 */
export function weekOverlaps(edges: CommunityEdgeRow[], week: string, groupIds: Iterable<string>): WeekOverlaps {
  const known = [...groupIds];
  const own = weekGraph(edges, week, "n_messages").internal;
  const weights = new Map(publishedTies(edges, week, known).map((tie) => [pairId(tie.a, tie.b), tie]));
  const overlaps = publishedTies(edges, week, known, "n_messages")
    .filter((tie) => tie.total > 0)
    .slice(0, OVERLAP_PAIRS)
    .map((tie): Overlap => {
      const ownA = own[tie.a] ?? 0;
      const ownB = own[tie.b] ?? 0;
      return {
        a: tie.a,
        b: tie.b,
        messages: tie.total,
        weight: weightOf(weights, tie),
        shareA: sideShare(tie.total, ownA),
        shareB: sideShare(tie.total, ownB),
        depth: overlapDepth(tie.total, ownA, ownB),
      };
    });
  const drawn = new Set(overlaps.map((o) => pairId(o.a, o.b)));
  const lines = [...weights.values()].filter((tie) => !drawn.has(pairId(tie.a, tie.b)));
  return { overlaps, lines };
}

/** Rule for one pair of centres: exactly `distance` apart, or at least `distance` apart. */
interface Constraint {
  a: number;
  b: number;
  distance: number;
  exact: boolean;
}

function radiusOf(radii: ReadonlyMap<string, number>, group: string): number {
  const radius = radii.get(group);
  if (radius === undefined) throw new Error(`no radius for group ${group}`);
  return radius;
}

/**
 * The smallest space between two discs in a layout (0 if any two touch or overlap): the gap the
 * Overlap mode keeps between every pair that does not overlap.
 */
export function smallestGap(positions: ReadonlyMap<string, Position>, radii: ReadonlyMap<string, number>): number {
  const placed = [...positions];
  let smallest = Infinity;
  placed.forEach(([a, p], i) => {
    for (const [b, q] of placed.slice(i + 1)) {
      smallest = Math.min(smallest, Math.hypot(p.x - q.x, p.y - q.y) - radiusOf(radii, a) - radiusOf(radii, b));
    }
  });
  return Number.isFinite(smallest) ? Math.max(smallest, 0) : 0;
}

/** Overlap pairs first, separations last, so separations win where the two pull against each other. */
function constraints(
  labels: readonly string[],
  radii: ReadonlyMap<string, number>,
  pairs: readonly OverlapPair[],
  gap: number,
): Constraint[] {
  const depths = new Map(pairs.map((p) => [pairId(p.a, p.b), p.depth]));
  const exact: Constraint[] = [];
  const apart: Constraint[] = [];
  labels.forEach((a, i) => {
    labels.slice(i + 1).forEach((b, offset) => {
      const radiusA = radiusOf(radii, a);
      const radiusB = radiusOf(radii, b);
      const depth = depths.get(pairId(a, b));
      if (depth === undefined) apart.push({ a: i, b: i + 1 + offset, distance: radiusA + radiusB + gap, exact: false });
      else exact.push({ a: i, b: i + 1 + offset, distance: targetDistance(radiusA, radiusB, depth), exact: true });
    });
  });
  return [...exact, ...apart];
}

/** Move both centres half the error along the line between them (along x if they coincide). */
function project(points: Position[], rule: Constraint): void {
  const p = points[rule.a];
  const q = points[rule.b];
  if (!p || !q) throw new Error("constraint names an unknown group");
  const dx = q.x - p.x;
  const dy = q.y - p.y;
  const current = Math.hypot(dx, dy);
  if (!rule.exact && current >= rule.distance) return;
  const [ux, uy] = current > 0 ? [dx / current, dy / current] : [1, 0];
  const half = (rule.distance - current) / 2;
  p.x -= ux * half;
  p.y -= uy * half;
  q.x += ux * half;
  q.y += uy * half;
}

/**
 * Week positions from the global layout: a fixed number of passes that pull each overlap pair to
 * its target distance and push every other pair to at least the sum of radii plus the global
 * layout's smallest gap, then passes that only push apart. Groups are visited in label order and
 * nothing is random, so the same data gives the same picture.
 */
export function relaxPositions(
  base: ReadonlyMap<string, Position>,
  radii: ReadonlyMap<string, number>,
  pairs: readonly OverlapPair[],
): Map<string, Position> {
  const labels = [...base.keys()].sort();
  const points = labels.map((label) => {
    const start = base.get(label);
    if (!start) throw new Error(`no position for group ${label}`);
    return { x: start.x, y: start.y };
  });
  const rules = constraints(labels, radii, pairs, smallestGap(base, radii));
  const apart = rules.filter((rule) => !rule.exact);
  for (let pass = 0; pass < OVERLAP_ITERATIONS; pass += 1) {
    for (const rule of rules) project(points, rule);
  }
  for (let pass = 0; pass < SEPARATION_PASSES; pass += 1) {
    for (const rule of apart) project(points, rule);
  }
  return new Map(
    labels.map((label, index) => {
      const point = points[index];
      if (!point) throw new Error(`solve lost group ${label}`);
      return [label, point];
    }),
  );
}

/** One overlap seen from one of its groups. */
export interface GroupOverlap {
  group: string;
  partner: string;
  messages: number;
  /** The shared messages' share of this group's side, then of the partner's. */
  share: number;
  partnerShare: number;
}

/** The overlaps a group takes part in this week, heaviest first, seen from that group. */
export function overlapsOf(overlaps: readonly Overlap[], group: string): GroupOverlap[] {
  return overlaps.flatMap((o): GroupOverlap[] => {
    if (o.a === group) return [{ group, partner: o.b, messages: o.messages, share: o.shareA, partnerShare: o.shareB }];
    if (o.b === group) return [{ group, partner: o.a, messages: o.messages, share: o.shareB, partnerShare: o.shareA }];
    return [];
  });
}
