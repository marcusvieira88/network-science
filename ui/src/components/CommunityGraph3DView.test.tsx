import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CommunityGraph } from "@/components/CommunityGraph";
import type { CommunityGraph3DProps } from "@/components/CommunityGraph3D";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";

// WebGL does not run in jsdom: the lazily loaded canvas is replaced by a stand-in that lists what
// it was asked to draw.
vi.mock("@/components/CommunityGraph3D", () => ({
  default: ({ nodes, links, layout, week }: CommunityGraph3DProps) => (
    <div data-testid="canvas-3d" data-week={week ?? ""}>
      {nodes.map((node) => (
        <span key={node.id} data-testid="group-node" data-size={node.val} />
      ))}
      {links.map((link) => (
        <span key={`${link.source}-${link.target}`} data-testid="tie-3d" data-width={link.width} />
      ))}
      <span data-testid="layout-ties">{layout.length}</span>
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
    <CommunityGraph groups={groups} edges={edges} weeks={weeks} events={[]} minGroupSize={minGroupSize} webgl />,
  );
}

describe("CommunityGraph with WebGL (3D)", () => {
  it("keeps the explanation, with spheres and k read from the data", async () => {
    const { container } = renderGraph(7);
    await screen.findByTestId("canvas-3d");
    expect(screen.getByText("Ties between groups, week by week")).toBeInTheDocument();
    expect(container).toHaveTextContent(
      "Each sphere is a group of at least 7 people, never an individual. Groups are fixed in the baseline period; " +
        "sphere volume follows group size and line width follows the weekly weight of messages between groups. " +
        "Group membership is not published.",
    );
  });

  it("draws one sphere per group sized by group size, and lays out on the ties of all weeks", async () => {
    renderGraph();
    await screen.findByTestId("canvas-3d");
    expect(screen.getAllByTestId("group-node").map((n) => n.getAttribute("data-size"))).toEqual(["14", "9", "6"]);
    expect(screen.getByTestId("layout-ties")).toHaveTextContent("2");
  });

  it("passes the selected week's ties to the canvas as the slider moves", async () => {
    renderGraph();
    const canvas = await screen.findByTestId("canvas-3d");
    expect(canvas).toHaveAttribute("data-week", "2000-01-03");
    expect(screen.getAllByTestId("tie-3d")).toHaveLength(1);
    const slider = screen.getByRole("slider", { name: "Week" });
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(canvas).toHaveAttribute("data-week", "2000-01-17");
    expect(screen.queryAllByTestId("tie-3d")).toHaveLength(0);
    expect(screen.getByText("No published tie between groups this week.")).toBeInTheDocument();
  });

  it("keeps the play control and the group table", async () => {
    renderGraph();
    await screen.findByTestId("canvas-3d");
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "People" })).toBeInTheDocument();
    expect(screen.getByText(/Drag to rotate, scroll to zoom/)).toBeInTheDocument();
  });
});
