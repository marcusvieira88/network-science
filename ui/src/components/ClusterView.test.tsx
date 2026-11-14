import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { View } from "@/App";
import { ClusterView } from "@/components/ClusterView";
import type { ClusterPeriods } from "@/lib/clusters";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";
import { sampleData } from "@/test/sample";

const groups: CommunityGroupRow[] = [
  { group: "G01", n_persons: 6 },
  { group: "G02", n_persons: 8 },
  { group: "other", n_persons: 5 },
];

function edge(week: string, src: string, dst: string, weight: number): CommunityEdgeRow {
  return { week, src_group: src, dst_group: dst, weight, n_messages: 10 };
}

// Baseline: G01 within 4, G01→G02 2, G02→G01 1, G02 within 3, G02→other 1.
// Crisis: G01→G02 3, G01 within 1.
const edges: CommunityEdgeRow[] = [
  edge("2000-01-03", "G01", "G01", 4),
  edge("2000-01-03", "G01", "G02", 2),
  edge("2000-01-03", "G02", "G01", 1),
  edge("2000-01-10", "G02", "G02", 3),
  edge("2000-01-10", "G02", "other", 1),
  edge("2001-08-20", "G01", "G02", 3),
  edge("2001-08-20", "G01", "G01", 1),
];

const periods: ClusterPeriods = {
  baseline: { start: "2000-01-01", end: "2000-12-31" },
  crisis: { start: "2001-08-14", end: "2001-12-02" },
};

function renderView(rows: CommunityEdgeRow[] = edges, onShowHypotheses = vi.fn(), driftCheck: boolean | null = false) {
  render(
    <ClusterView
      groups={groups}
      edges={rows}
      periods={periods}
      minGroupSize={5}
      driftCheck={driftCheck}
      onShowHypotheses={onShowHypotheses}
    />,
  );
  return onShowHypotheses;
}

function tableRow(group: string): HTMLElement {
  const row = screen.getAllByRole("row").find((r) => within(r).queryAllByRole("cell")[0]?.textContent === group);
  if (!row) throw new Error(`no table row for ${group}`);
  return row;
}

function arcOf(group: string): HTMLElement {
  const arc = screen.getAllByTestId("group-arc").find((a) => a.getAttribute("data-group") === group);
  if (!arc) throw new Error(`no arc for ${group}`);
  return arc;
}

describe("ClusterView", () => {
  it("says that each segment is a group of at least k people", () => {
    renderView();
    expect(
      screen.getByText(/Each segment is a group of at least 5 people, never an individual/),
    ).toBeInTheDocument();
  });

  it("offers the three periods and starts on all weeks", () => {
    renderView();
    const tabs = within(screen.getByRole("tablist", { name: "Period" })).getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Baseline year", "Crisis weeks", "All weeks"]);
    expect(screen.getByRole("tab", { name: "All weeks" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("period-weeks")).toHaveTextContent("Every week · 3 weeks with published ties");
  });

  it("shows the per-group table for the selected period", async () => {
    renderView();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Baseline year" }));
    expect(screen.getByTestId("period-weeks")).toHaveTextContent(
      "2000-01-01 to 2000-12-31, weeks overlapping it · 2 weeks with published ties",
    );
    // G02: total 3 + (2 + 1) + 1 = 7, within 3 -> 42.9%; its only partner group is G01 (3): the
    // outside bucket is not a group, so it is never listed as a partner.
    expect(within(tableRow("G02")).getAllByRole("cell").map((c) => c.textContent)).toEqual([
      "G02",
      "8",
      "42.9%",
      "G01 (3)",
    ]);
    await user.click(screen.getByRole("tab", { name: "Crisis weeks" }));
    // The outside bucket: last, greyed, its size, and neither a within-group share nor partners.
    const outside = tableRow("Outside the 2000 groups");
    expect(within(outside).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Outside the 2000 groups", "5", "—", "—"]);
    expect(outside).toHaveAttribute("data-outside", "true");
    expect(screen.getAllByRole("row").at(-1)).toBe(outside);
    // `other` has no weight in the crisis weeks: no arc for it.
    expect(screen.getAllByTestId("group-arc").map((a) => a.getAttribute("data-group"))).toEqual(["G01", "G02"]);
  });

  it("explains the outside bucket and gives each period's share of weight involving outside people", async () => {
    renderView();
    expect(screen.getByTestId("outside-note")).toHaveTextContent(
      "Outside the 2000 groups: 5 people with no tie in 2000 (such as people who first appear later) or in groups under 5 people; not a community.",
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Baseline year" }));
    // Baseline weight: 4 + 2 + 1 + 3 + 1 = 11, of which 1 (G02 -> other) involves the bucket.
    expect(screen.getByTestId("outside-share")).toHaveTextContent(
      "9.1% of this period's weight involves people outside the 2000 groups.",
    );
    await user.click(screen.getByRole("tab", { name: "Crisis weeks" }));
    expect(screen.getByTestId("outside-share")).toHaveTextContent(
      "0% of this period's weight involves people outside the 2000 groups.",
    );
  });

  it("draws the outside bucket as a hatched grey arc labelled 'outside', described as no community", async () => {
    renderView();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Baseline year" }));
    const arc = arcOf("other");
    expect(arc).toHaveAttribute("aria-label", "Outside the 2000 groups");
    expect(arc.querySelector("path")?.getAttribute("fill")).toMatch(/^url\(#/);
    expect(arc).toHaveTextContent("outside");
    fireEvent.mouseEnter(arc);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Outside the 2000 groups · 5 people · total weight 1 · not a community",
    );
    const ribbon = screen.getAllByTestId("ribbon").find((r) => r.getAttribute("aria-label") === "Between G02 and Outside the 2000 groups");
    if (!ribbon) throw new Error("no G02–outside ribbon");
    fireEvent.focus(ribbon);
    expect(screen.getByRole("status")).toHaveTextContent("G02 ↔ outside · G02 → outside: 1 · outside → G02: 0");
  });

  it("shows a group's size, total weight and within-group share on hover", async () => {
    renderView();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Baseline year" }));
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Hover or focus");
    fireEvent.mouseEnter(arcOf("G01"));
    expect(status).toHaveTextContent("Group G01 · 6 people · total weight 7 · 57.1% stays within the group");
    fireEvent.mouseLeave(arcOf("G01"));
    expect(status).toHaveTextContent("Hover or focus");
  });

  it("shows the weight in each direction when a ribbon is focused", async () => {
    renderView();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Baseline year" }));
    const ribbon = screen.getAllByTestId("ribbon").find((r) => r.getAttribute("aria-label") === "Between G01 and G02");
    if (!ribbon) throw new Error("no G01–G02 ribbon");
    fireEvent.focus(ribbon);
    expect(screen.getByRole("status")).toHaveTextContent("G01 ↔ G02 · G01 → G02: 2 · G02 → G01: 1");
    const self = screen.getAllByTestId("ribbon").find((r) => r.getAttribute("aria-label") === "Within G02");
    if (!self) throw new Error("no within-G02 ribbon");
    fireEvent.mouseEnter(self);
    expect(screen.getByRole("status")).toHaveTextContent("Within group G02 · weight 3");
  });

  it("names the group whose cross-group share changed most, without a causal claim", () => {
    // The fixture's weights are scaled by 100 so both groups pass MIN_COMPARABLE_WEIGHT (50);
    // shares are unchanged by scaling.
    const scaled = edges.map((e) => ({ ...e, weight: e.weight === null ? null : e.weight * 100 }));
    const onShowHypotheses = renderView(scaled);
    const line = screen.getByTestId("what-changed");
    // G02 cross-group share among real groups: 3/6 = 50% in the baseline year (its 1 to outside
    // people is left out), 3/3 = 100% in the crisis weeks.
    expect(line).toHaveTextContent(
      "the cross-group share of group G02 changed most: from 50% to 100% (+50 percentage points)",
    );
    expect(line).toHaveTextContent("counted between groups only; mail with outside people is left out");
    expect(line).toHaveTextContent("only groups with a weight of at least 50 in both periods are compared");
    expect(line).toHaveTextContent("it does not say why they changed");
    expect(line).toHaveTextContent("The groups were fixed on the baseline year");
    expect(line).toHaveTextContent("The H2 artifact check (baseline placebo) found this drift large enough to explain H2");
    expect(line.textContent ?? "").not.toMatch(/\b(caused|because of|due to|led to)\b/i);
    fireEvent.click(within(line).getByRole("button", { name: "Hypotheses view" }));
    expect(onShowHypotheses).toHaveBeenCalledOnce();
  });

  it("reports the drift check as the release has it", () => {
    renderView(edges, vi.fn(), true);
    expect(screen.getByTestId("what-changed")).toHaveTextContent("did not find drift that large, but the caveat still applies");
  });

  it("says when the drift check did not run", () => {
    renderView(edges, vi.fn(), null);
    expect(screen.getByTestId("what-changed")).toHaveTextContent("did not run in this release");
  });

  it("mentions the hatched arc only when the release has an outside bucket", () => {
    render(
      <ClusterView
        groups={groups.filter((g) => g.group !== "other")}
        edges={edges.filter((e) => e.dst_group !== "other")}
        periods={periods}
        minGroupSize={5}
        driftCheck={false}
        onShowHypotheses={vi.fn()}
      />,
    );
    expect(screen.queryByText(/hatched grey arc/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("outside-note")).not.toBeInTheDocument();
  });

  it("says when there is nothing to compare or draw", async () => {
    renderView([edge("2000-01-03", "G01", "G02", 2)]);
    expect(screen.getByTestId("what-changed")).toHaveTextContent("there is nothing to compare");
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Crisis weeks" }));
    expect(screen.getByText("No published tie between groups in this period.")).toBeInTheDocument();
    expect(screen.queryAllByTestId("group-arc")).toHaveLength(0);
  });

  it("explains instead of crashing when the release lacks the baseline period", () => {
    const data = sampleData();
    const parameters = { ...data.run.parameters, baseline_start: undefined };
    render(<View view="clusters" data={{ ...data, run: { ...data.run, parameters } }} onSelect={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("lack the baseline period");
  });
});
