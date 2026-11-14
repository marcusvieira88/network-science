import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommunityGraph } from "@/components/CommunityGraph";
import { PLAY_INTERVAL_MS } from "@/components/TimeSlider";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";
import { layoutGroups, maxWeeklyTie, namedGroups, publishedTies, weekGraph } from "@/lib/network";

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
const BASELINE = { start: "2000-01-01", end: "2000-12-31" };

// The same groups plus the release's outside bucket, and week 2000-01-03 with mail to it.
// Hand-computed n_messages that week: 10 + 10 + 10 (named rows) + 10 + 10 + 50 (touching other)
// = 100, so 70% involves outside people.
const withOutside: CommunityGroupRow[] = [...groups, { group: "other", n_persons: 25838 }];
const outsideEdges: CommunityEdgeRow[] = [
  ...edges,
  edge("2000-01-03", "G01", "other", 30),
  edge("2000-01-03", "other", "G02", 2),
  { week: "2000-01-03", src_group: "other", dst_group: "other", weight: 40, n_messages: 50 },
];

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

describe("the outside bucket in the network helpers", () => {
  it("is not a named group", () => {
    expect(namedGroups(withOutside)).toEqual(groups);
  });

  it("never forms a published tie, even when passed as a group", () => {
    expect(publishedTies(outsideEdges, "2000-01-03", ["G01", "G02", "G03", "other"])).toEqual([
      { a: "G01", b: "G02", weightAB: 4, weightBA: 1.5, total: 5.5 },
    ]);
  });

  it("does not set the tie width scale", () => {
    expect(maxWeeklyTie(outsideEdges, weeks, withOutside.map((g) => g.group))).toBe(5.5);
  });

  it("is not placed by the 2D layout, which places the real groups exactly as without it", () => {
    expect(layoutGroups(withOutside, outsideEdges, 640, 420)).toEqual(layoutGroups(groups, edges, 640, 420));
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
    return render(
      <CommunityGraph groups={groups} edges={edges} weeks={weeks} events={[]} minGroupSize={5} seed={1} baseline={BASELINE} webgl={false} />,
    );
  }

  function renderWithOutside() {
    return render(
      <CommunityGraph
        groups={withOutside}
        edges={outsideEdges}
        weeks={weeks}
        events={[]}
        minGroupSize={5}
        seed={1}
        baseline={BASELINE}
        webgl={false}
      />,
    );
  }

  function nodePositions(container: HTMLElement): string[] {
    return [...container.querySelectorAll("[data-testid=group-node] circle")].map(
      (c) => `${c.getAttribute("cx")},${c.getAttribute("cy")}`,
    );
  }

  it("explains how to read the chart and sums up the selected week in one sentence", () => {
    renderGraph();
    expect(screen.getByText("How to read this")).toBeInTheDocument();
    const busiest = weekGraph(edges, weeks[0] ?? null).ties[0];
    expect(screen.getByTestId("week-summary")).toHaveTextContent(`the busiest link between groups was ${busiest?.a} ↔ ${busiest?.b}`);
  });

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

  it("in the Individuals mode draws one bare point per person inside each group's circle", async () => {
    const user = userEvent.setup();
    const { container } = renderGraph();
    expect(screen.queryByTestId("anonymous-points")).not.toBeInTheDocument();
    const before = nodePositions(container);
    await user.click(screen.getByRole("tab", { name: "Individuals (anonymous)" }));
    const layer = screen.getByTestId("anonymous-points");
    const points = [...layer.querySelectorAll("circle")];
    expect(points).toHaveLength(14 + 9 + 5);
    // Every point lies inside a group circle; the groups have not moved.
    expect(nodePositions(container)).toEqual(before);
    const circles = [...container.querySelectorAll("[data-testid=group-node] circle")].map((c) => ({
      x: Number(c.getAttribute("cx")),
      y: Number(c.getAttribute("cy")),
      r: Number(c.getAttribute("r")),
    }));
    for (const point of points) {
      const x = Number(point.getAttribute("cx"));
      const y = Number(point.getAttribute("cy"));
      expect(circles.some((c) => Math.hypot(x - c.x, y - c.y) < c.r)).toBe(true);
    }
    expect(screen.getAllByTestId("group-node")).toHaveLength(3);
    expect(container).toHaveTextContent("Each point stands for one person in a group of at least 5;");
  });

  it("draws no circle for the outside bucket and says above the graph how much of the week's mail involves it", () => {
    renderWithOutside();
    expect(screen.getAllByTestId("group-node")).toHaveLength(3);
    expect(screen.getAllByTestId("tie")).toHaveLength(1);
    expect(screen.getByTestId("outside-caption")).toHaveTextContent(
      "70% of this week's mail (counted per sender–recipient pair) involves people outside the 2000 groups.",
    );
    expect(screen.getByTestId("outside-caption")).toHaveTextContent(
      "Outside the 2000 groups: 25,838 people with no tie in 2000 (mostly people who first appear later) or in groups under 5 people; not a community.",
    );
    // The week sentence names a link between real groups only.
    expect(screen.getByTestId("week-summary")).toHaveTextContent("the busiest link between groups was G01 ↔ G02 (weight 5.5); 1 pair");
  });

  it("lists ties between real groups and the ties to outside people as one summary line", () => {
    renderWithOutside();
    const table = screen.getByRole("table", { name: "Strongest ties this week" });
    const rows = within(table).getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(rows).toEqual(["G01 ↔ G025.5", "Any group ↔ outside (2 groups)32"]);
    expect(within(table).getAllByRole("row").at(-1)).toHaveAttribute("data-outside", "true");
  });

  it("lists the outside bucket last and greyed in the groups table, as no community", () => {
    renderWithOutside();
    const table = screen.getByRole("table", { name: "Groups" });
    const last = within(table).getAllByRole("row").at(-1);
    expect(last).toHaveAttribute("data-outside", "true");
    expect(last?.textContent).toBe("Outside the 2000 groups25,83840");
  });

  it("draws no anonymous point for anyone outside the groups in the Individuals mode", async () => {
    const user = userEvent.setup();
    renderWithOutside();
    await user.click(screen.getByRole("tab", { name: "Individuals (anonymous)" }));
    expect(screen.getByTestId("anonymous-points").querySelectorAll("circle")).toHaveLength(14 + 9 + 5);
  });

  it("shows no outside caption when the release has no outside bucket", () => {
    renderGraph();
    expect(screen.queryByTestId("outside-caption")).not.toBeInTheDocument();
  });

  it("shows only group label, size and weights", () => {
    const { container } = renderGraph();
    const text = container.textContent ?? "";
    expect(text).toContain("G01");
    expect(text).toContain("14");
    expect(text).not.toMatch(/p_[a-z2-7]{16}|@/);
  });
});
