import { describe, expect, it } from "vitest";

import type { CommunityEdgeRow } from "@/lib/data";
import {
  OVERLAP_MAX_DEPTH,
  OVERLAP_PAIRS,
  overlapDepth,
  overlapsOf,
  relaxPositions,
  sideShare,
  smallestGap,
  targetDistance,
  weekOverlaps,
} from "@/lib/overlap";

const WEEK = "2001-10-22";

function row(src: string, dst: string, n_messages: number | null, weight: number | null = n_messages): CommunityEdgeRow {
  return { week: WEEK, src_group: src, dst_group: dst, weight, n_messages };
}

function distance(positions: ReadonlyMap<string, { x: number; y: number }>, a: string, b: string): number {
  const p = positions.get(a);
  const q = positions.get(b);
  if (!p || !q) throw new Error(`missing ${a} or ${b}`);
  return Math.hypot(p.x - q.x, p.y - q.y);
}

describe("overlap depth", () => {
  it("is the shared share of the less internally active side (real week 2001-10-22: G05 98, G13 984, shared 217)", () => {
    expect(sideShare(217, 98)).toBeCloseTo(217 / 315, 10);
    expect(sideShare(217, 98)).toBeCloseTo(0.69, 2);
    expect(sideShare(217, 984)).toBeCloseTo(217 / 1201, 10);
    // The pair's depth follows the side with fewer own messages, then the cap.
    expect(overlapDepth(217, 98, 984)).toBeCloseTo(217 / 315, 10);
    expect(overlapDepth(217, 984, 98)).toBeCloseTo(217 / 315, 10);
  });

  it("is clamped to [0, 1] and capped at the named maximum", () => {
    expect(sideShare(0, 0)).toBe(0);
    expect(sideShare(10, 0)).toBe(1);
    expect(overlapDepth(10, 0, 50)).toBe(OVERLAP_MAX_DEPTH);
    expect(OVERLAP_MAX_DEPTH).toBeLessThan(1);
    expect(overlapDepth(0, 5, 5)).toBe(0);
  });

  it("puts the centres at r_a + r_b minus depth times the smaller diameter", () => {
    expect(targetDistance(10, 4, 0)).toBe(14);
    expect(targetDistance(10, 4, 0.5)).toBe(10);
    expect(targetDistance(4, 10, 0.8)).toBeCloseTo(14 - 6.4, 10);
  });
});

describe("weekly overlap selection", () => {
  const groups = ["A", "B", "C", "D", "E", "F", "G", "H"];
  // Eight pairs with distinct counts, one tie at 30 (C-D and B-E), the `other` bucket and a
  // suppressed row that must not count.
  const edges: CommunityEdgeRow[] = [
    row("A", "B", 50),
    row("B", "A", 10),
    row("A", "C", 40),
    row("C", "D", 30),
    row("E", "B", 30),
    row("A", "D", 20),
    row("F", "G", 15),
    row("G", "H", 12),
    row("H", "A", 5),
    row("A", "other", 999),
    row("other", "B", 999),
    row("F", "H", null),
    row("A", "A", 100),
    row("B", "B", 7),
    { week: "2001-10-29", src_group: "G", dst_group: "H", weight: 900, n_messages: 900 },
  ];

  it(`takes the ${OVERLAP_PAIRS} heaviest published pairs by messages, ties broken by label`, () => {
    expect(OVERLAP_PAIRS).toBe(6);
    const { overlaps } = weekOverlaps(edges, WEEK, groups);
    expect(overlaps.map((o) => `${o.a}-${o.b}:${o.messages}`)).toEqual([
      "A-B:60",
      "A-C:40",
      "B-E:30",
      "C-D:30",
      "A-D:20",
      "F-G:15",
    ]);
  });

  it("never takes the outside bucket into a pair, even when it is passed as a group", () => {
    const withOther = weekOverlaps(edges, WEEK, [...groups, "other"]);
    expect(withOther).toEqual(weekOverlaps(edges, WEEK, groups));
    expect(withOther.lines.some((tie) => tie.a === "other" || tie.b === "other")).toBe(false);
  });

  it("keeps the remaining published ties as ordinary lines, as the Groups mode draws them", () => {
    const { lines } = weekOverlaps(edges, WEEK, groups);
    // A suppressed row counts as 0, as publishedTies counts it; the other bucket never appears.
    expect(lines.map((tie) => `${tie.a}-${tie.b}:${tie.total}`)).toEqual(["G-H:12", "A-H:5", "F-H:0"]);
  });

  it("reports both sides' shares and the drawn depth from within-group messages", () => {
    const first = weekOverlaps(edges, WEEK, groups).overlaps[0];
    expect(first).toMatchObject({ a: "A", b: "B", messages: 60 });
    expect(first?.shareA).toBeCloseTo(60 / 160, 10);
    expect(first?.shareB).toBeCloseTo(60 / 67, 10);
    expect(first?.depth).toBeCloseTo(Math.min(60 / 67, OVERLAP_MAX_DEPTH), 10);
  });

  it("draws nothing in a week without published ties", () => {
    expect(weekOverlaps(edges, "1999-01-04", groups)).toEqual({ overlaps: [], lines: [] });
  });
});

describe("distance-constraint solve", () => {
  const radii = new Map([
    ["A", 10],
    ["B", 4],
    ["C", 6],
    ["D", 3],
  ]);
  const base = new Map([
    ["A", { x: 0, y: 0 }],
    ["B", { x: 40, y: 0 }],
    ["C", { x: 0, y: 40 }],
    ["D", { x: 1, y: 30 }],
  ]);
  const pairs = [{ a: "A", b: "B", depth: 0.5 }];

  it("measures the layout's smallest gap between two discs (C and D here), never below 0", () => {
    expect(smallestGap(base, radii)).toBeCloseTo(Math.sqrt(101) - 9, 10);
    expect(smallestGap(new Map([["A", { x: 0, y: 0 }], ["B", { x: 1, y: 0 }]]), radii)).toBe(0);
    expect(smallestGap(new Map([["A", { x: 0, y: 0 }]]), radii)).toBe(0);
  });

  it("brings an overlap pair to its target distance", () => {
    const relaxed = relaxPositions(base, radii, pairs);
    expect(distance(relaxed, "A", "B")).toBeCloseTo(targetDistance(10, 4, 0.5), 2);
  });

  it("keeps every other pair at least the sum of radii plus the layout's smallest gap apart", () => {
    const relaxed = relaxPositions(base, radii, pairs);
    const gap = smallestGap(base, radii);
    for (const [a, b] of [
      ["A", "C"],
      ["A", "D"],
      ["B", "C"],
      ["B", "D"],
      ["C", "D"],
    ] as const) {
      expect(distance(relaxed, a, b)).toBeGreaterThanOrEqual((radii.get(a) ?? 0) + (radii.get(b) ?? 0) + gap - 1e-6);
    }
  });

  it("leaves a layout that already satisfies every constraint unchanged", () => {
    expect(relaxPositions(new Map([...base].filter(([k]) => k !== "D")), radii, [])).toEqual(
      new Map([...base].filter(([k]) => k !== "D")),
    );
  });

  it("separates two coincident centres deterministically", () => {
    const relaxed = relaxPositions(new Map([["A", { x: 0, y: 0 }], ["B", { x: 0, y: 0 }]]), radii, []);
    expect(distance(relaxed, "A", "B")).toBeCloseTo(14, 6);
  });

  it("is deterministic: the same input gives exactly the same positions, whatever the order", () => {
    const first = relaxPositions(base, radii, pairs);
    const reversed = relaxPositions(new Map([...base].reverse()), new Map([...radii].reverse()), [...pairs]);
    expect(relaxPositions(base, radii, pairs)).toEqual(first);
    expect(reversed).toEqual(first);
  });
});

describe("one group's overlaps", () => {
  const overlaps = [
    { a: "A", b: "B", messages: 60, weight: 6, shareA: 0.375, shareB: 0.9, depth: 0.8 },
    { a: "B", b: "C", messages: 40, weight: 4, shareA: 0.4, shareB: 0.5, depth: 0.5 },
  ];

  it("lists each partner with the pair's messages and the group's share first", () => {
    expect(overlapsOf(overlaps, "B")).toEqual([
      { group: "B", partner: "A", messages: 60, share: 0.9, partnerShare: 0.375 },
      { group: "B", partner: "C", messages: 40, share: 0.4, partnerShare: 0.5 },
    ]);
    expect(overlapsOf(overlaps, "D")).toEqual([]);
  });
});
