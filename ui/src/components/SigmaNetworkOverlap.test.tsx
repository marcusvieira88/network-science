import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SigmaNetwork, { type SigmaNetworkProps } from "@/components/SigmaNetwork";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";
import { relaxPositions, smallestGap, targetDistance, weekOverlaps } from "@/lib/overlap";
import { groupKey, groupNodeRadius, layoutPositions } from "@/lib/sigmaNetwork";
import { resetSigmaStub, sigmaStub } from "@/test/reactSigma";
import { applyThemeVariables } from "@/test/theme";

vi.mock("@react-sigma/core", () => import("@/test/reactSigma"));
// The week-to-week motion is Sigma's tween; here it lands on its targets at once, so tests see
// where each group ends up.
const animated = vi.hoisted(() => ({ calls: 0 }));
vi.mock("sigma/utils", () => ({
  animateNodes: (
    graph: { mergeNodeAttributes: (key: string, attributes: Record<string, number>) => void },
    targets: Record<string, Record<string, number>>,
  ) => {
    animated.calls += 1;
    for (const [key, target] of Object.entries(targets)) graph.mergeNodeAttributes(key, target);
    return () => undefined;
  },
}));

const groups: CommunityGroupRow[] = [
  { group: "G01", n_persons: 16 },
  { group: "G02", n_persons: 9 },
  { group: "G03", n_persons: 4 },
];
const WEEK = "2001-10-22";
const edges: CommunityEdgeRow[] = [
  { week: WEEK, src_group: "G01", dst_group: "G02", weight: 3, n_messages: 30 },
  { week: WEEK, src_group: "G02", dst_group: "G01", weight: 1, n_messages: 10 },
  { week: WEEK, src_group: "G01", dst_group: "G01", weight: 9, n_messages: 60 },
  { week: WEEK, src_group: "G02", dst_group: "G02", weight: 2, n_messages: 40 },
  { week: WEEK, src_group: "G02", dst_group: "other", weight: 50, n_messages: 500 },
  { week: "2001-10-29", src_group: "G02", dst_group: "G03", weight: 2, n_messages: 5 },
];
const props: SigmaNetworkProps = { groups, edges, week: WEEK, maxTie: 4, mode: "overlap", seed: 3 };

function loaded() {
  if (!sigmaStub.graph) throw new Error("no graph loaded");
  return sigmaStub.graph;
}

function centres(): Map<string, { x: number; y: number }> {
  const graph = loaded();
  return new Map(graph.nodes().map((key) => [key, { x: graph.getNodeAttribute(key, "x"), y: graph.getNodeAttribute(key, "y") }]));
}

function gap(a: string, b: string): number {
  const p = centres().get(groupKey(a));
  const q = centres().get(groupKey(b));
  if (!p || !q) throw new Error("missing group");
  return Math.hypot(p.x - q.x, p.y - q.y);
}

describe("SigmaNetwork, Overlap mode", () => {
  beforeEach(() => {
    resetSigmaStub();
    applyThemeVariables();
    animated.calls = 0;
  });

  it("places groups by the week's relaxed layout: the overlapping pair at its depth, the rest apart", () => {
    render(<SigmaNetwork {...props} />);
    const radii = new Map(groups.map((g) => [g.group, groupNodeRadius(g.n_persons)]));
    const { overlaps } = weekOverlaps(edges, WEEK, radii.keys());
    const expected = relaxPositions(layoutPositions(groups, edges), radii, overlaps);
    for (const [group, position] of expected) expect(centres().get(groupKey(group))).toEqual(position);
    // 40 shared, own 60 and 40: depth 40 / (40 + 40) = 0.5 of the smaller diameter.
    expect(gap("G01", "G02")).toBeCloseTo(targetDistance(4, 3, 0.5), 2);
    const kept = smallestGap(layoutPositions(groups, edges), radii);
    expect(gap("G01", "G03")).toBeGreaterThanOrEqual(4 + 2 + kept - 1e-6);
    expect(gap("G02", "G03")).toBeGreaterThanOrEqual(3 + 2 + kept - 1e-6);
    expect(loaded().getNodeAttribute(groupKey("G01"), "color")).toMatch(/^#[0-9a-f]{6}80$/);
    expect(loaded().getEdgeAttribute(loaded().edges()[0] ?? "", "hidden")).toBe(true);
  });

  it("draws the same picture for the same data", () => {
    const { unmount } = render(<SigmaNetwork {...props} />);
    const first = centres();
    unmount();
    resetSigmaStub();
    render(<SigmaNetwork {...props} />);
    expect(centres()).toEqual(first);
  });

  it("moves the groups to the next week's layout with Sigma's animation", () => {
    const { rerender } = render(<SigmaNetwork {...props} />);
    expect(animated.calls).toBe(0);
    rerender(<SigmaNetwork {...props} week="2001-10-29" />);
    expect(animated.calls).toBe(1);
    const radii = new Map(groups.map((g) => [g.group, groupNodeRadius(g.n_persons)]));
    const next = relaxPositions(layoutPositions(groups, edges), radii, weekOverlaps(edges, "2001-10-29", radii.keys()).overlaps);
    for (const [group, position] of next) expect(centres().get(groupKey(group))).toEqual(position);
  });

  it("explains in the legend that an overlap is mail, not shared members", () => {
    render(<SigmaNetwork {...props} />);
    expect(screen.getByTestId("network-legend")).toHaveTextContent(
      "Overlap = mail between two groups, not shared members — each person is in exactly one group.",
    );
  });

  it("shows the pair's message count and both sides' percentages when a group is hovered", () => {
    render(<SigmaNetwork {...props} />);
    act(() => sigmaStub.handlers.enterNode?.({ node: groupKey("G02") }));
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Group G02 · 9 people");
    expect(status).toHaveTextContent("G02 ↔ G01 · 40 messages · 50% of G02's mail · 40% of G01's mail");
  });

  it("draws nothing to overlap in a week with no published tie", () => {
    render(<SigmaNetwork {...props} week={null} />);
    expect(loaded().size).toBe(0);
    expect(loaded().order).toBe(groups.length);
  });

  it("leaves the Groups mode exactly as before: no motion, opaque discs, global positions", () => {
    render(<SigmaNetwork {...props} mode="groups" />);
    const layout = layoutPositions(groups, edges);
    for (const [group, position] of layout) expect(centres().get(groupKey(group))).toEqual(position);
    expect(loaded().getNodeAttribute(groupKey("G01"), "color")).toMatch(/^#[0-9a-f]{6}$/);
    expect(animated.calls).toBe(0);
  });
});
