import { describe, expect, it } from "vitest";

import { MAX_PARTICLES, MAX_PARTICLE_SPEED, MIN_PARTICLE_SPEED, cellRadius } from "@/lib/cells";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";
import {
  EDGE_MAX_OPACITY,
  EDGE_MAX_WIDTH,
  EDGE_MIN_OPACITY,
  EDGE_MIN_WIDTH,
  NODE_MAX_LIGHTNESS,
  NODE_MIN_LIGHTNESS,
  graphNodes,
  layoutLinks,
  nodeLabel,
  weekLinks,
} from "@/lib/network3d";
import { maxWeeklyTie } from "@/lib/network";

const groups: CommunityGroupRow[] = [
  { group: "G02", n_persons: 9 },
  { group: "G01", n_persons: 27 },
  { group: "G03", n_persons: 5 },
];

function edge(week: string, src: string, dst: string, weight: number | null): CommunityEdgeRow {
  return { week, src_group: src, dst_group: dst, weight, n_messages: weight === null ? null : 10 };
}

const edges: CommunityEdgeRow[] = [
  edge("2000-01-03", "G01", "G02", 6),
  edge("2000-01-03", "G02", "G01", 2),
  edge("2000-01-03", "G01", "G01", 7),
  edge("2000-01-10", "G02", "G03", 4),
  edge("2000-01-10", "G03", "G02", null),
];
const weeks = ["2000-01-03", "2000-01-10", "2000-01-17"];

describe("graphNodes", () => {
  it("gives one cell per group, sorted, with volume equal to group size", () => {
    const nodes = graphNodes(groups);
    expect(nodes.map((n) => [n.id, n.nPersons, n.val])).toEqual([
      ["G01", 27, 27],
      ["G02", 9, 9],
      ["G03", 5, 5],
    ]);
    // 27 people: radius 3 times cube root 27 = 9; 8 times the volume of a 27/8-person cell.
    expect(nodes[0]?.radius).toBe(9);
    expect(nodes.map((n) => n.radius)).toEqual([27, 9, 5].map(cellRadius));
  });

  it("makes larger groups lighter, in the accent hue, from the smallest to the largest lightness", () => {
    const [big, mid, small] = graphNodes(groups);
    expect(big?.color).toBe(`hsl(213, 76%, ${NODE_MAX_LIGHTNESS.toFixed(1)}%)`);
    expect(small?.color).toBe(`hsl(213, 76%, ${NODE_MIN_LIGHTNESS.toFixed(1)}%)`);
    // 9 persons lies (cbrt 9 - cbrt 5) / (cbrt 27 - cbrt 5) of the way up, on a cube-root scale.
    const share = (Math.cbrt(9) - Math.cbrt(5)) / (3 - Math.cbrt(5));
    const lightness = NODE_MIN_LIGHTNESS + share * (NODE_MAX_LIGHTNESS - NODE_MIN_LIGHTNESS);
    expect(mid?.color).toBe(`hsl(213, 76%, ${lightness.toFixed(1)}%)`);
  });

  it("uses the middle lightness when every group has the same size", () => {
    const [only] = graphNodes([{ group: "G01", n_persons: 8 }]);
    expect(only?.color).toBe(`hsl(213, 76%, ${((NODE_MIN_LIGHTNESS + NODE_MAX_LIGHTNESS) / 2).toFixed(1)}%)`);
  });
});

describe("weekLinks", () => {
  it("draws the week's ties between groups with width and opacity scaled to the heaviest weekly tie", () => {
    const max = maxWeeklyTie(edges, weeks);
    expect(max).toBe(8);
    expect(weekLinks(edges, "2000-01-03", max, ["G01", "G02", "G03"])).toEqual([
      {
        source: "G01",
        target: "G02",
        weight: 8,
        width: EDGE_MAX_WIDTH,
        color: `rgba(157, 194, 242, ${EDGE_MAX_OPACITY.toFixed(3)})`,
        particles: MAX_PARTICLES,
        particleSpeed: MAX_PARTICLE_SPEED,
      },
    ]);
    const half = weekLinks(edges, "2000-01-10", max, ["G01", "G02", "G03"]);
    expect(half).toEqual([
      {
        source: "G02",
        target: "G03",
        weight: 4,
        width: EDGE_MIN_WIDTH + 0.5 * (EDGE_MAX_WIDTH - EDGE_MIN_WIDTH),
        color: `rgba(157, 194, 242, ${(EDGE_MIN_OPACITY + 0.5 * (EDGE_MAX_OPACITY - EDGE_MIN_OPACITY)).toFixed(3)})`,
        // Half the heaviest weight: half of six particles, at the middle speed.
        particles: 3,
        particleSpeed: (MIN_PARTICLE_SPEED + MAX_PARTICLE_SPEED) / 2,
      },
    ]);
    expect(weekLinks(edges, "2000-01-17", max, ["G01", "G02", "G03"])).toEqual([]);
  });

  it("drops ties to a group that is not published", () => {
    expect(weekLinks(edges, "2000-01-10", 8, ["G01", "G02"])).toEqual([]);
  });
});

describe("layoutLinks", () => {
  it("uses the ties of all weeks so the layout does not depend on the selected week", () => {
    expect(layoutLinks(groups, edges).map((l) => [l.source, l.target])).toEqual([
      ["G01", "G02"],
      ["G02", "G03"],
    ]);
  });
});

describe("nodeLabel", () => {
  it("names the group and its size only, with markup escaped", () => {
    const [node] = graphNodes([{ group: "<b>G1</b>", n_persons: 12 }]);
    if (!node) throw new Error("no node");
    expect(nodeLabel(node)).toBe("Group &lt;b&gt;G1&lt;/b&gt; · 12 people");
  });
});
