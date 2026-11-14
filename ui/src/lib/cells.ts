/**
 * Pure mapping for the network's group-size dots mode: the anonymous points drawn inside each group.
 *
 * The points only show how many people a group has: one point per person counted in a published
 * group, at a seeded random position that carries no information. They are not real individuals. They have no label or data; where the
 * renderer needs a key, it is an opaque sequence number.
 */
import type { CommunityGroupRow } from "@/lib/data";

/** Points stay this share of the radius away from the membrane, so none sits on the edge. */
export const POINT_MARGIN = 0.15;

export const NETWORK_MODES = ["groups", "dots", "overlap"] as const;
export type NetworkMode = (typeof NETWORK_MODES)[number];

export type Point = readonly [number, number];

/** Groups in label order: the order groups are drawn and points are seeded in. */
export function sortedGroups(groups: CommunityGroupRow[]): CommunityGroupRow[] {
  return [...groups].sort((x, y) => x.group.localeCompare(y.group));
}

/** Total anonymous points the group-size dots mode draws: one per person in a published group. */
export function totalPoints(groups: CommunityGroupRow[]): number {
  return groups.reduce((sum, group) => sum + group.n_persons, 0);
}

/** mulberry32 (its published constants): a small seeded generator, so the same seed always scatters the same points. */
export function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * `count` points uniformly inside a disc of the given radius, centred on the origin, kept
 * POINT_MARGIN of the radius inside the edge. Rejection sampling from the enclosing square keeps
 * the density uniform.
 */
export function scatterPoints(count: number, radius: number, seed: number): Point[] {
  const random = seededRandom(seed);
  const inner = radius * (1 - POINT_MARGIN);
  const points: Point[] = [];
  while (points.length < count) {
    const x = (2 * random() - 1) * inner;
    const y = (2 * random() - 1) * inner;
    if (Math.hypot(x, y) <= inner) points.push([x, y]);
  }
  return points;
}

/** A prime stride between run seeds, so neighbouring run seeds never share a group's seed. */
const SEED_STRIDE = 1000003;

/** One seed per group, from the run seed and the group's place in label order. */
export function groupSeed(runSeed: number, groupIndex: number): number {
  return (Math.imul(runSeed, SEED_STRIDE) + groupIndex) >>> 0;
}

/**
 * The anonymous points of every published group, keyed by group label: `n_persons` points each,
 * scattered inside the group's radius (`radiusOf(n_persons)`). Purely illustrative.
 */
export function anonymousPoints(
  groups: CommunityGroupRow[],
  runSeed: number,
  radiusOf: (nPersons: number) => number,
): Map<string, Point[]> {
  return new Map(
    sortedGroups(groups).map((group, index) => [
      group.group,
      scatterPoints(group.n_persons, radiusOf(group.n_persons), groupSeed(runSeed, index)),
    ]),
  );
}
