import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CommunityGraph } from "@/components/CommunityGraph";
import type { SigmaNetworkProps } from "@/components/SigmaNetwork";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";

// WebGL does not run in jsdom: the lazily loaded Sigma view is replaced by a stand-in that lists
// what it was asked to draw.
vi.mock("@/components/SigmaNetwork", () => ({
  default: ({ groups, edges, week, maxTie, mode }: SigmaNetworkProps) => (
    <div data-testid="sigma-view" data-week={week ?? ""} data-mode={mode} data-max-tie={maxTie} data-edges={edges.length}>
      {groups.map((g) => (
        <span key={g.group} data-testid="group-node" data-size={g.n_persons} />
      ))}
    </div>
  ),
}));

const groups: CommunityGroupRow[] = [
  { group: "G01", n_persons: 14 },
  { group: "G02", n_persons: 9 },
  { group: "G03", n_persons: 6 },
];
const edges: CommunityEdgeRow[] = [
  { week: "2000-01-03", src_group: "G01", dst_group: "G02", weight: 4, n_messages: 10 },
  { week: "2000-01-10", src_group: "G02", dst_group: "G03", weight: 2, n_messages: 10 },
];
const weeks = ["2000-01-03", "2000-01-10", "2000-01-17"];

function renderGraph(minGroupSize = 6) {
  return render(
    <CommunityGraph groups={groups} edges={edges} weeks={weeks} events={[]} minGroupSize={minGroupSize} seed={3} baseline={null} webgl />,
  );
}

describe("CommunityGraph with WebGL (Sigma.js)", () => {
  it("keeps the explanation, with k read from the data", async () => {
    const { container } = renderGraph(7);
    await screen.findByTestId("sigma-view");
    expect(screen.getByText("Ties between groups, week by week")).toBeInTheDocument();
    expect(container).toHaveTextContent(
      "Each circle is a group of at least 7 people, never an individual. Groups are fixed in the baseline period; " +
        "circle area follows group size and line width follows the weekly weight of messages between groups. " +
        "Group membership is not published.",
    );
    expect(screen.getByText(/Hover a group, or search for its label/)).toBeInTheDocument();
  });

  it("switches between Groups and anonymous Individuals, explaining the points with k from the data", async () => {
    const user = userEvent.setup();
    const { container } = renderGraph(7);
    const view = await screen.findByTestId("sigma-view");
    expect(view).toHaveAttribute("data-mode", "groups");
    expect(container).not.toHaveTextContent("Each point stands for one person");
    await user.click(screen.getByRole("tab", { name: "Individuals (anonymous)" }));
    expect(view).toHaveAttribute("data-mode", "individuals");
    expect(container).toHaveTextContent(
      "Each point stands for one person in a group of at least 7; points are anonymous and their positions and " +
        "links are illustrative, not individual data. Ties are measured between groups only.",
    );
    await user.click(screen.getByRole("tab", { name: "Groups" }));
    expect(view).toHaveAttribute("data-mode", "groups");
  });

  it("passes every group, all edges, the selected week and one tie scale for all weeks", async () => {
    renderGraph();
    const view = await screen.findByTestId("sigma-view");
    expect(screen.getAllByTestId("group-node").map((n) => n.getAttribute("data-size"))).toEqual(["14", "9", "6"]);
    expect(view).toHaveAttribute("data-edges", "2");
    expect(view).toHaveAttribute("data-max-tie", "4");
    expect(view).toHaveAttribute("data-week", "2000-01-03");
    const slider = screen.getByRole("slider", { name: "Week" });
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(view).toHaveAttribute("data-week", "2000-01-17");
    expect(screen.getByText("No published tie between groups this week.")).toBeInTheDocument();
  });

  it("never hands the outside bucket to the WebGL view, so it gets no disc, layout place, overlap or legend size", async () => {
    render(
      <CommunityGraph
        groups={[...groups, { group: "other", n_persons: 25838 }]}
        edges={[...edges, { week: "2000-01-03", src_group: "G01", dst_group: "other", weight: 40, n_messages: 90 }]}
        weeks={weeks}
        events={[]}
        minGroupSize={6}
        seed={3}
        baseline={{ start: "2000-01-01", end: "2000-12-31" }}
        webgl
      />,
    );
    const view = await screen.findByTestId("sigma-view");
    expect(screen.getAllByTestId("group-node").map((n) => n.getAttribute("data-size"))).toEqual(["14", "9", "6"]);
    // The tie scale ignores the 40 to the outside bucket.
    expect(view).toHaveAttribute("data-max-tie", "4");
    expect(screen.getByTestId("outside-caption")).toHaveTextContent("90% of this week's mail");
  });

  it("keeps the play control and the group table", async () => {
    renderGraph();
    await screen.findByTestId("sigma-view");
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "People" })).toBeInTheDocument();
  });

  it("offers the Overlap mode and says an overlap is mail, not shared members", async () => {
    const user = userEvent.setup();
    const { container } = renderGraph();
    const view = await screen.findByTestId("sigma-view");
    await user.click(screen.getByRole("tab", { name: "Overlap" }));
    expect(view).toHaveAttribute("data-mode", "overlap");
    expect(container).toHaveTextContent(
      "Overlap = mail between two groups, not shared members — each person is in exactly one group.",
    );
  });
});
