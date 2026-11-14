/**
 * Pure mapping for the "cells" network view: cell sizes, the anonymous points drawn inside each
 * group in the Individuals mode, and the signal particles along each tie. No three.js here, so
 * this module stays out of the lazily loaded 3D chunk's dependencies.
 *
 * The anonymous points are decoration: one point per person counted in a published group, at a
 * seeded random position that carries no information. They have no id, label or data.
 */
import type { CommunityGroupRow } from "@/lib/data";

/** Cell radius = cube root of group size times this, so cell volume is proportional to size. */
export const CELL_RADIUS_PER_CBRT_PERSON = 3;
/** Points stay this share of the radius away from the membrane, so none sits on the edge. */
export const POINT_MARGIN = 0.15;

/** Signal particles: a tie at the heaviest weekly weight carries the most and fastest particles. */
export const MAX_PARTICLES = 6;
export const MIN_PARTICLE_SPEED = 0.002;
export const MAX_PARTICLE_SPEED = 0.012;

export const NETWORK_MODES = ["groups", "individuals"] as const;
export type NetworkMode = (typeof NETWORK_MODES)[number];

export type Point = readonly number[];

export function cellRadius(nPersons: number): number {
  return CELL_RADIUS_PER_CBRT_PERSON * Math.cbrt(nPersons);
}

/** Share of the heaviest weekly tie, clamped to [0, 1]. */
function weightShare(weight: number, maxTie: number): number {
  return Math.min(Math.max(weight / Math.max(maxTie, 1), 0), 1);
}

/** No particle on an empty tie; otherwise at least one, rising to MAX_PARTICLES at the heaviest. */
export function particleCount(weight: number, maxTie: number): number {
  if (weight <= 0) return 0;
  return Math.max(1, Math.ceil(weightShare(weight, maxTie) * MAX_PARTICLES));
}

export function particleSpeed(weight: number, maxTie: number): number {
  return MIN_PARTICLE_SPEED + weightShare(weight, maxTie) * (MAX_PARTICLE_SPEED - MIN_PARTICLE_SPEED);
}

/** Groups in label order: the order cells are drawn and points are seeded in. */
export function sortedGroups(groups: CommunityGroupRow[]): CommunityGroupRow[] {
  return [...groups].sort((x, y) => x.group.localeCompare(y.group));
}

/** Total anonymous points the Individuals mode draws: one per person in a published group. */
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
 * `count` points uniformly inside a disc (2 dimensions) or ball (3) of the given radius, centred
 * on the origin, kept POINT_MARGIN of the radius inside the edge. Rejection sampling from the
 * enclosing square or cube keeps the density uniform.
 */
export function scatterPoints(count: number, radius: number, dimensions: 2 | 3, seed: number): Point[] {
  const random = seededRandom(seed);
  const inner = radius * (1 - POINT_MARGIN);
  const points: Point[] = [];
  while (points.length < count) {
    const point = Array.from({ length: dimensions }, () => (2 * random() - 1) * inner);
    if (Math.hypot(...point) <= inner) points.push(point);
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
  dimensions: 2 | 3,
  runSeed: number,
  radiusOf: (nPersons: number) => number,
): Map<string, Point[]> {
  return new Map(
    sortedGroups(groups).map((group, index) => [
      group.group,
      scatterPoints(group.n_persons, radiusOf(group.n_persons), dimensions, groupSeed(runSeed, index)),
    ]),
  );
}

/** Opacity at the centre of the glow sprite; it falls to zero at the edge. */
const MAX_ALPHA = 255;

/**
 * RGBA pixels of a soft round glow, `size` × `size`: white, with opacity falling from the centre
 * to zero at the edge on a squared curve. Used as the halo and point sprite texture.
 */
export function glowPixels(size: number): Uint8Array {
  const pixels = new Uint8Array(size * size * 4);
  const centre = (size - 1) / 2;
  for (let row = 0; row < size; row += 1) {
    for (let column = 0; column < size; column += 1) {
      const distance = Math.min(Math.hypot(column - centre, row - centre) / (size / 2), 1);
      const offset = (row * size + column) * 4;
      pixels.fill(MAX_ALPHA, offset, offset + 3);
      pixels[offset + 3] = Math.round(MAX_ALPHA * (1 - distance) ** 2);
    }
  }
  return pixels;
}
