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
    // G02: total 3 + (2 + 1) + 1 = 7, within 3 -> 42.9%; partners G01 (3), other (1).
    expect(within(tableRow("G02")).getAllByRole("cell").map((c) => c.textContent)).toEqual([
      "G02",
      "8",
      "42.9%",
      "G01 (3), other (1)",
    ]);
    await user.click(screen.getByRole("tab", { name: "Crisis weeks" }));
    expect(within(tableRow("other")).getAllByRole("cell").map((c) => c.textContent)).toEqual([
      "other",
      "5",
      "n/a",
      "—",
    ]);
    // `other` has no weight in the crisis weeks: no arc for it.
    expect(screen.getAllByTestId("group-arc").map((a) => a.getAttribute("data-group"))).toEqual(["G01", "G02"]);
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
    const onShowHypotheses = renderView();
    const line = screen.getByTestId("what-changed");
    // G02 cross-group share: 4/7 = 57.1% in the baseline year, 3/3 = 100% in the crisis weeks.
    expect(line).toHaveTextContent(
      "the cross-group share of group G02 changed most: from 57.1% to 100% (+42.9 percentage points)",
    );
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
