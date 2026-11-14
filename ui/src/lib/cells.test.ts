import { describe, expect, it } from "vitest";

import { POINT_MARGIN, anonymousPoints, groupSeed, scatterPoints, seededRandom, totalPoints } from "@/lib/cells";
import type { CommunityGroupRow } from "@/lib/data";

const groups: CommunityGroupRow[] = [
  { group: "G02", n_persons: 9 },
  { group: "G01", n_persons: 27 },
  { group: "G03", n_persons: 5 },
];

/** Any radius rule will do here: the points must stay inside whatever radius the view draws. */
const radius = (nPersons: number): number => 2 * Math.sqrt(nPersons);

describe("seededRandom", () => {
  it("is mulberry32: the reference implementation's first draws for seed 1", () => {
    // Computed independently with 32-bit integer arithmetic in Python.
    const random = seededRandom(1);
    expect([random(), random(), random()]).toEqual([0.6270739405881613, 0.002735721180215478, 0.5274470399599522]);
  });

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
  it("puts exactly count points inside the radius, less the margin", () => {
    const points = scatterPoints(40, 10, 3);
    expect(points).toHaveLength(40);
    for (const [x, y] of points) expect(Math.hypot(x, y)).toBeLessThanOrEqual(10 * (1 - POINT_MARGIN));
  });

  it("is deterministic for a seed", () => {
    expect(scatterPoints(12, 5, 42)).toEqual(scatterPoints(12, 5, 42));
    expect(scatterPoints(12, 5, 42)).not.toEqual(scatterPoints(12, 5, 43));
  });

  it("returns no point for an empty group", () => {
    expect(scatterPoints(0, 5, 1)).toEqual([]);
  });
});

describe("anonymousPoints", () => {
  it("gives every published group exactly n_persons points inside its radius", () => {
    const points = anonymousPoints(groups, 11, radius);
    expect([...points.keys()]).toEqual(["G01", "G02", "G03"]);
    expect([...points.values()].map((p) => p.length)).toEqual([27, 9, 5]);
    expect([...points.values()].flat()).toHaveLength(totalPoints(groups));
    expect(totalPoints(groups)).toBe(41);
    for (const [x, y] of points.get("G01") ?? []) expect(Math.hypot(x, y)).toBeLessThan(radius(27));
  });

  it("does not depend on the row order and seeds each group apart", () => {
    const forward = anonymousPoints(groups, 11, radius);
    expect(anonymousPoints([...groups].reverse(), 11, radius)).toEqual(forward);
    expect(groupSeed(11, 0)).not.toBe(groupSeed(11, 1));
    expect(groupSeed(11, 0)).not.toBe(groupSeed(12, 0));
  });
});
