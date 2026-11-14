import { describe, expect, it } from "vitest";

import {
  MAX_PARTICLES,
  MAX_PARTICLE_SPEED,
  MIN_PARTICLE_SPEED,
  POINT_MARGIN,
  anonymousPoints,
  cellRadius,
  glowPixels,
  groupSeed,
  particleCount,
  particleSpeed,
  scatterPoints,
  seededRandom,
  totalPoints,
} from "@/lib/cells";
import type { CommunityGroupRow } from "@/lib/data";

const groups: CommunityGroupRow[] = [
  { group: "G02", n_persons: 9 },
  { group: "G01", n_persons: 27 },
  { group: "G03", n_persons: 5 },
];

describe("cellRadius", () => {
  it("makes cell volume proportional to group size", () => {
    expect(cellRadius(27)).toBe(9);
    expect(cellRadius(1)).toBe(3);
    // Eight times the people, twice the radius, eight times the volume.
    expect(cellRadius(64) / cellRadius(8)).toBeCloseTo(2, 12);
  });
});

describe("particleCount and particleSpeed", () => {
  it("send no particle along an empty tie", () => {
    expect(particleCount(0, 10)).toBe(0);
  });

  it("scale count and speed with the share of the heaviest weekly tie", () => {
    expect(particleCount(10, 10)).toBe(MAX_PARTICLES);
    expect(particleCount(5, 10)).toBe(3);
    // A tiny tie still shows one signal.
    expect(particleCount(0.01, 10)).toBe(1);
    expect(particleSpeed(10, 10)).toBe(MAX_PARTICLE_SPEED);
    expect(particleSpeed(0, 10)).toBe(MIN_PARTICLE_SPEED);
    expect(particleSpeed(2.5, 10)).toBeCloseTo(MIN_PARTICLE_SPEED + 0.25 * (MAX_PARTICLE_SPEED - MIN_PARTICLE_SPEED), 12);
  });

  it("never exceed the maximum when a week is heavier than the scale", () => {
    expect(particleCount(30, 10)).toBe(MAX_PARTICLES);
    expect(particleSpeed(30, 10)).toBe(MAX_PARTICLE_SPEED);
  });
});

describe("seededRandom", () => {
  it("repeats for the same seed, differs for another, and stays in [0, 1)", () => {
    const a = seededRandom(7);
    const b = seededRandom(7);
    const c = seededRandom(8);
    const first = Array.from({ length: 50 }, () => a());
    expect(Array.from({ length: 50 }, () => b())).toEqual(first);
    expect(Array.from({ length: 50 }, () => c())).not.toEqual(first);
    for (const value of first) {
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThan(1);
    }
  });
});

describe("scatterPoints", () => {
  it.each([2, 3] as const)("puts exactly count points inside the radius in %i dimensions", (dimensions) => {
    const points = scatterPoints(40, 10, dimensions, 3);
    expect(points).toHaveLength(40);
    for (const point of points) {
      expect(point).toHaveLength(dimensions);
      expect(Math.hypot(...point)).toBeLessThanOrEqual(10 * (1 - POINT_MARGIN));
    }
  });

  it("is deterministic for a seed", () => {
    expect(scatterPoints(12, 5, 3, 42)).toEqual(scatterPoints(12, 5, 3, 42));
    expect(scatterPoints(12, 5, 3, 42)).not.toEqual(scatterPoints(12, 5, 3, 43));
  });

  it("returns no point for an empty group", () => {
    expect(scatterPoints(0, 5, 2, 1)).toEqual([]);
  });
});

describe("anonymousPoints", () => {
  it("gives every published group exactly n_persons points inside its radius", () => {
    const points = anonymousPoints(groups, 3, 11, cellRadius);
    expect([...points.keys()]).toEqual(["G01", "G02", "G03"]);
    expect([...points.values()].map((p) => p.length)).toEqual([27, 9, 5]);
    expect([...points.values()].flat()).toHaveLength(totalPoints(groups));
    expect(totalPoints(groups)).toBe(41);
    for (const point of points.get("G01") ?? []) expect(Math.hypot(...point)).toBeLessThan(cellRadius(27));
  });

  it("does not depend on the row order and seeds each group apart", () => {
    const forward = anonymousPoints(groups, 2, 11, cellRadius);
    expect(anonymousPoints([...groups].reverse(), 2, 11, cellRadius)).toEqual(forward);
    expect(groupSeed(11, 0)).not.toBe(groupSeed(11, 1));
    expect(groupSeed(11, 0)).not.toBe(groupSeed(12, 0));
  });
});

describe("glowPixels", () => {
  it("is white, opaque at the centre and transparent at the corners, fading outwards", () => {
    const size = 9;
    const pixels = glowPixels(size);
    expect(pixels).toHaveLength(size * size * 4);
    const alpha = (column: number, row: number) => pixels[(row * size + column) * 4 + 3];
    expect(alpha(4, 4)).toBe(255);
    expect(alpha(0, 0)).toBe(0);
    expect(alpha(4, 0)).toBe(Math.round(255 * (1 - 4 / 4.5) ** 2));
    expect(alpha(4, 2)).toBeGreaterThan(alpha(4, 1) ?? 255);
    expect([...pixels.slice(0, 3)]).toEqual([255, 255, 255]);
  });
});
