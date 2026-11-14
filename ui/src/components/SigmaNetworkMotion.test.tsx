import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SigmaNetwork, { type SigmaNetworkProps } from "@/components/SigmaNetwork";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";
import { relaxPositions, weekOverlaps } from "@/lib/overlap";
import { type Position, groupKey, groupNodeRadius, layoutPositions } from "@/lib/sigmaNetwork";
import { resetSigmaStub } from "@/test/reactSigma";
import { applyThemeVariables } from "@/test/theme";

vi.mock("@react-sigma/core", () => import("@/test/reactSigma"));
vi.mock("@sigma/layer-webgl", () => import("@/test/layerWebgl"));

/**
 * Sigma's tween, cut off half-way: each move records where every node starts, puts the nodes
 * half-way to their targets (where they are drawn when the next week arrives) and counts its
 * cancellation.
 */
const motion = vi.hoisted(() => ({ starts: [] as Map<string, { x: number; y: number }>[], cancels: 0 }));
vi.mock("sigma/utils", () => ({
  animateNodes: (
    graph: {
      getNodeAttribute: (key: string, name: string) => number;
      mergeNodeAttributes: (key: string, attributes: Record<string, number>) => void;
    },
    targets: Record<string, { x: number; y: number }>,
  ) => {
    const start = new Map<string, { x: number; y: number }>();
    for (const [key, target] of Object.entries(targets)) {
      const from = { x: graph.getNodeAttribute(key, "x"), y: graph.getNodeAttribute(key, "y") };
      start.set(key, from);
      graph.mergeNodeAttributes(key, { x: (from.x + target.x) / 2, y: (from.y + target.y) / 2 });
    }
    motion.starts.push(start);
    return () => {
      motion.cancels += 1;
    };
  },
}));

const groups: CommunityGroupRow[] = [
  { group: "G01", n_persons: 16 },
  { group: "G02", n_persons: 9 },
  { group: "G03", n_persons: 4 },
];
const WEEK_A = "2001-10-22";
const WEEK_B = "2001-10-29";
const WEEK_C = "2001-11-05";
const edges: CommunityEdgeRow[] = [
  { week: WEEK_A, src_group: "G01", dst_group: "G02", weight: 3, n_messages: 40 },
  { week: WEEK_A, src_group: "G01", dst_group: "G01", weight: 9, n_messages: 60 },
  { week: WEEK_A, src_group: "G02", dst_group: "G02", weight: 2, n_messages: 40 },
  { week: WEEK_B, src_group: "G02", dst_group: "G03", weight: 2, n_messages: 30 },
  { week: WEEK_B, src_group: "G02", dst_group: "G02", weight: 2, n_messages: 20 },
  { week: WEEK_B, src_group: "G03", dst_group: "G03", weight: 2, n_messages: 10 },
];
const props: SigmaNetworkProps = { groups, edges, week: WEEK_A, maxTie: 4, mode: "overlap", seed: 3 };

function weekPositions(week: string): ReadonlyMap<string, Position> {
  const radii = new Map(groups.map((g) => [g.group, groupNodeRadius(g.n_persons)]));
  return relaxPositions(layoutPositions(groups, edges), radii, weekOverlaps(edges, week, radii.keys()).overlaps);
}

function position(positions: ReadonlyMap<string, Position>, group: string): Position {
  const found = positions.get(group);
  if (!found) throw new Error("missing group");
  return found;
}

describe("SigmaNetwork, Overlap mode, a week change during the move", () => {
  beforeEach(() => {
    resetSigmaStub();
    applyThemeVariables();
    motion.starts = [];
    motion.cancels = 0;
  });

  it("cancels the running move and starts the next one from where the groups are drawn", () => {
    const { rerender } = render(<SigmaNetwork {...props} />);
    rerender(<SigmaNetwork {...props} week={WEEK_B} />);
    rerender(<SigmaNetwork {...props} week={WEEK_C} />);
    expect(motion.starts).toHaveLength(2);
    expect(motion.cancels).toBe(1);
    const [a, b] = [weekPositions(WEEK_A), weekPositions(WEEK_B)];
    const second = motion.starts[1];
    for (const g of groups) {
      const from = position(a, g.group);
      const to = position(b, g.group);
      const halfWay = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
      expect(second?.get(groupKey(g.group))).toEqual(halfWay);
    }
    // The fixture moves G03 between the weeks, so half-way is not the first move's target.
    expect(second?.get(groupKey("G03"))).not.toEqual(position(b, "G03"));
  });
});
