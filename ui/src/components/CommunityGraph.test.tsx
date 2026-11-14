import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommunityGraph } from "@/components/CommunityGraph";
import { PLAY_INTERVAL_MS } from "@/components/TimeSlider";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";
import { layoutGroups, weekGraph } from "@/lib/network";

const groups: CommunityGroupRow[] = [
  { group: "G01", n_persons: 14 },
  { group: "G02", n_persons: 9 },
  { group: "G03", n_persons: 5 },
];

function edge(week: string, src: string, dst: string, weight: number | null): CommunityEdgeRow {
  return { week, src_group: src, dst_group: dst, weight, n_messages: weight === null ? null : 10 };
}

const edges: CommunityEdgeRow[] = [
  edge("2000-01-03", "G01", "G02", 4),
  edge("2000-01-03", "G02", "G01", 1.5),
  edge("2000-01-03", "G01", "G01", 7),
  edge("2000-01-10", "G02", "G03", 2),
  edge("2000-01-10", "G03", "G02", null),
];
const weeks = ["2000-01-03", "2000-01-10", "2000-01-17"];

describe("weekGraph", () => {
  it("sums both directions per pair, keeps within-group weight apart and treats suppressed as 0", () => {
    expect(weekGraph(edges, "2000-01-03")).toEqual({
      ties: [{ a: "G01", b: "G02", weightAB: 4, weightBA: 1.5, total: 5.5 }],
      internal: { G01: 7 },
    });
    expect(weekGraph(edges, "2000-01-10").ties).toEqual([
      { a: "G02", b: "G03", weightAB: 2, weightBA: 0, total: 2 },
    ]);
    expect(weekGraph(edges, "2000-01-17")).toEqual({ ties: [], internal: {} });
  });
});

describe("layoutGroups", () => {
  it("is deterministic and inside the canvas", () => {
    const first = layoutGroups(groups, edges, 640, 420);
    const second = layoutGroups([...groups].reverse(), [...edges].reverse(), 640, 420);
    expect(second).toEqual(first);
    for (const node of first) {
      expect(node.x - node.radius).toBeGreaterThanOrEqual(0);
      expect(node.x + node.radius).toBeLessThanOrEqual(640);
      expect(node.y - node.radius).toBeGreaterThanOrEqual(0);
      expect(node.y + node.radius).toBeLessThanOrEqual(420);
    }
  });

  it("sizes groups by number of people", () => {
    const radii = layoutGroups(groups, edges, 640, 420).map((node) => node.radius);
    expect([...radii].sort((a, b) => b - a)).toEqual(radii);
    expect(new Set(radii).size).toBe(3);
  });
});

describe("CommunityGraph without WebGL (2D fallback)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  function renderGraph() {
    return render(<CommunityGraph groups={groups} edges={edges} weeks={weeks} events={[]} minGroupSize={5} webgl={false} />);
  }

  function nodePositions(container: HTMLElement): string[] {
    return [...container.querySelectorAll("[data-testid=group-node] circle")].map(
      (c) => `${c.getAttribute("cx")},${c.getAttribute("cy")}`,
    );
  }

  it("draws one node per group and states that nodes are groups, not individuals", () => {
    const { container } = renderGraph();
    expect(screen.getAllByTestId("group-node")).toHaveLength(3);
    expect(container).toHaveTextContent("Each circle is a group of at least 5 people, never an individual.");
  });

  it("keeps node positions fixed while the week changes, and redraws the ties", () => {
    const { container } = renderGraph();
    const before = nodePositions(container);
    expect(screen.getAllByTestId("tie")).toHaveLength(1);
    expect(screen.getByRole("img")).toHaveAccessibleName("Group network for the week of 2000-01-03");
    fireEvent.keyDown(screen.getByRole("slider", { name: "Week" }), { key: "ArrowRight" });
    expect(screen.getByRole("img")).toHaveAccessibleName("Group network for the week of 2000-01-10");
    expect(nodePositions(container)).toEqual(before);
    fireEvent.keyDown(screen.getByRole("slider", { name: "Week" }), { key: "ArrowRight" });
    expect(screen.queryAllByTestId("tie")).toHaveLength(0);
    expect(container).toHaveTextContent("No published tie between groups this week.");
  });

  it("plays through the weeks and stops at the end", () => {
    vi.useFakeTimers();
    renderGraph();
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    act(() => {
      vi.advanceTimersByTime(PLAY_INTERVAL_MS);
    });
    expect(screen.getByRole("status")).toHaveTextContent("2000-01-10");
    act(() => {
      vi.advanceTimersByTime(PLAY_INTERVAL_MS * 5);
    });
    expect(screen.getByRole("status")).toHaveTextContent("2000-01-17");
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
  });

  it("shows only group label, size and weights", () => {
    const { container } = renderGraph();
    const text = container.textContent ?? "";
    expect(text).toContain("G01");
    expect(text).toContain("14");
    expect(text).not.toMatch(/p_[a-z2-7]{16}|@/);
  });
});
