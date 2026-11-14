import { describe, expect, it } from "vitest";

import {
  type ClusterPeriods,
  clusterMatrix,
  groupSummaries,
  largestCrossShareChange,
  periodRange,
  periodWeeks,
  weekInPeriod,
} from "@/lib/clusters";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";

const groups: CommunityGroupRow[] = [
  { group: "other", n_persons: 5 },
  { group: "G02", n_persons: 8 },
  { group: "G01", n_persons: 6 },
];

function edge(week: string, src: string, dst: string, weight: number | null): CommunityEdgeRow {
  return { week, src_group: src, dst_group: dst, weight, n_messages: weight === null ? null : 10 };
}

const edges: CommunityEdgeRow[] = [
  edge("2000-01-03", "G01", "G01", 4),
  edge("2000-01-03", "G01", "G02", 2),
  edge("2000-01-03", "G02", "G01", 1),
  edge("2000-01-10", "G02", "G02", 3),
  edge("2000-01-10", "G02", "other", 1),
  edge("2000-01-10", "other", "G02", null),
  // Monday before the crisis start (a Tuesday): outside the crisis weeks.
  edge("2001-08-13", "G02", "G02", 9),
  edge("2001-08-20", "G01", "G02", 3),
  edge("2001-08-20", "G01", "G01", 1),
  // Monday after the crisis end.
  edge("2001-12-03", "G02", "G02", 5),
];

const periods: ClusterPeriods = {
  baseline: { start: "2000-01-01", end: "2000-12-31" },
  crisis: { start: "2001-08-14", end: "2001-12-02" },
};

describe("periods", () => {
  it("resolves each option to its date range, all weeks to no range", () => {
    expect(periodRange("baseline", periods)).toEqual(periods.baseline);
    expect(periodRange("crisis", periods)).toEqual(periods.crisis);
    expect(periodRange("all", periods)).toBeNull();
  });

  it("puts a week in a period when its Monday falls inside it, ends included", () => {
    expect(weekInPeriod("2001-08-13", periods.crisis)).toBe(false);
    expect(weekInPeriod("2001-08-20", periods.crisis)).toBe(true);
    expect(weekInPeriod("2001-12-03", periods.crisis)).toBe(false);
    expect(weekInPeriod("2000-12-31", periods.baseline)).toBe(true);
    expect(weekInPeriod("1999-12-27", periods.baseline)).toBe(false);
    expect(weekInPeriod("1999-12-27", null)).toBe(true);
  });

  it("lists the distinct weeks with published ties in a period, in order", () => {
    expect(periodWeeks(edges, periods.baseline)).toEqual(["2000-01-03", "2000-01-10"]);
    expect(periodWeeks(edges, periods.crisis)).toEqual(["2001-08-20"]);
    expect(periodWeeks(edges, null)).toHaveLength(5);
  });
});

describe("clusterMatrix", () => {
  it("sums weights per direction over the period, suppressed as 0, other group last", () => {
    const matrix = clusterMatrix(groups, edges, periods.baseline);
    expect(matrix.groups).toEqual(["G01", "G02", "other"]);
    expect(matrix.sizes).toEqual([6, 8, 5]);
    expect(matrix.directed).toEqual([
      [4, 2, 0],
      [1, 3, 1],
      [0, 0, 0],
    ]);
    // Both directions summed between two groups; the diagonal is the within-group weight once.
    expect(matrix.symmetric).toEqual([
      [4, 3, 0],
      [3, 3, 1],
      [0, 1, 0],
    ]);
  });

  it("covers all weeks when there is no range", () => {
    expect(clusterMatrix(groups, edges, null).directed).toEqual([
      [5, 5, 0],
      [1, 17, 1],
      [0, 0, 0],
    ]);
  });

  it("refuses a tie to a group that is not published", () => {
    expect(() => clusterMatrix(groups, [edge("2000-01-03", "G01", "G09", 1)], null)).toThrow(/G09/);
  });
});

describe("groupSummaries", () => {
  it("gives size, total, within-group share and the top partners by weight", () => {
    const summaries = groupSummaries(clusterMatrix(groups, edges, periods.baseline));
    expect(summaries).toEqual([
      { group: "G01", nPersons: 6, total: 7, within: 4, withinShare: 4 / 7, partners: [{ group: "G02", weight: 3 }] },
      {
        group: "G02",
        nPersons: 8,
        total: 7,
        within: 3,
        withinShare: 3 / 7,
        partners: [
          { group: "G01", weight: 3 },
          { group: "other", weight: 1 },
        ],
      },
      { group: "other", nPersons: 5, total: 1, within: 0, withinShare: 0, partners: [{ group: "G02", weight: 1 }] },
    ]);
  });

  it("keeps at most three partners, heaviest first, ties by label", () => {
    const five: CommunityGroupRow[] = ["A", "B", "C", "D", "E"].map((group) => ({ group, n_persons: 5 }));
    const star = [
      edge("2000-01-03", "A", "B", 1),
      edge("2000-01-03", "A", "C", 2),
      edge("2000-01-03", "D", "A", 2),
      edge("2000-01-03", "A", "E", 0.5),
    ];
    const [a] = groupSummaries(clusterMatrix(five, star, null));
    expect(a?.partners).toEqual([
      { group: "C", weight: 2 },
      { group: "D", weight: 2 },
      { group: "B", weight: 1 },
    ]);
  });

  it("has no within-group share for a group without weight in the period", () => {
    const summaries = groupSummaries(clusterMatrix(groups, edges, periods.crisis));
    expect(summaries.map((s) => [s.group, s.total, s.withinShare])).toEqual([
      ["G01", 4, 1 / 4],
      ["G02", 3, 0],
      ["other", 0, null],
    ]);
  });
});

describe("largestCrossShareChange", () => {
  it("finds the group whose cross-group share moved most between two periods", () => {
    const before = groupSummaries(clusterMatrix(groups, edges, periods.baseline));
    const after = groupSummaries(clusterMatrix(groups, edges, periods.crisis));
    // G01: 3/7 -> 3/4 (+0.32); G02: 4/7 -> 1 (+0.43); other has no weight in the crisis.
    const change = largestCrossShareChange(before, after);
    expect(change?.group).toBe("G02");
    expect(change?.before).toBeCloseTo(4 / 7);
    expect(change?.after).toBe(1);
    expect(change?.change).toBeCloseTo(3 / 7);
  });

  it("counts a fall as much as a rise", () => {
    const before = groupSummaries(clusterMatrix(groups, edges, periods.crisis));
    const after = groupSummaries(clusterMatrix(groups, edges, periods.baseline));
    expect(largestCrossShareChange(before, after)).toMatchObject({ group: "G02", before: 1 });
    expect(largestCrossShareChange(before, after)?.change).toBeCloseTo(-3 / 7);
  });

  it("is null when no group has weight in both periods", () => {
    const empty = groupSummaries(clusterMatrix(groups, [], null));
    const before = groupSummaries(clusterMatrix(groups, edges, periods.baseline));
    expect(largestCrossShareChange(before, empty)).toBeNull();
  });
});
