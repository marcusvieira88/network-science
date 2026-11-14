import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SigmaNetwork, { type SigmaNetworkProps } from "@/components/SigmaNetwork";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";
import { edgeWidth, groupKey, groupNodeRadius, layoutPositions, pointKey } from "@/lib/sigmaNetwork";
import { drawnEdge, drawnNode, resetSigmaStub, sigmaStub } from "@/test/reactSigma";
import { applyThemeVariables } from "@/test/theme";

// Sigma needs WebGL, which jsdom lacks: React Sigma is replaced by a stand-in that keeps what the
// view hands it (graph, settings, events).
vi.mock("@react-sigma/core", () => import("@/test/reactSigma"));
// The real package reads WebGL2RenderingContext on import, which jsdom lacks.
vi.mock("@sigma/layer-webgl", () => import("@/test/layerWebgl"));

const groups: CommunityGroupRow[] = [
  { group: "G01", n_persons: 14 },
  { group: "G02", n_persons: 9 },
  { group: "G03", n_persons: 6 },
];
const edges: CommunityEdgeRow[] = [
  { week: "2000-01-03", src_group: "G01", dst_group: "G02", weight: 4, n_messages: 10 },
  { week: "2000-01-10", src_group: "G02", dst_group: "G03", weight: 2, n_messages: 10 },
];

const props: SigmaNetworkProps = { groups, edges, week: "2000-01-03", maxTie: 4, mode: "groups", seed: 3 };

function loaded() {
  if (!sigmaStub.graph) throw new Error("no graph loaded");
  return sigmaStub.graph;
}

describe("SigmaNetwork", () => {
  beforeEach(() => {
    resetSigmaStub();
    applyThemeVariables();
  });

  it("loads one disc per group at the layout's positions and the week's ties", () => {
    render(<SigmaNetwork {...props} />);
    const graph = loaded();
    const layout = layoutPositions(groups, edges);
    expect(graph.nodes()).toEqual(["group:G01", "group:G02", "group:G03"]);
    for (const g of groups) {
      expect(graph.getNodeAttributes(groupKey(g.group))).toMatchObject({
        ...layout.get(g.group),
        size: groupNodeRadius(g.n_persons),
        label: g.group,
      });
    }
    expect(graph.edges().map((key) => graph.extremities(key))).toEqual([["group:G01", "group:G02"]]);
    expect(graph.getEdgeAttribute(graph.edges()[0] ?? "", "size")).toBe(edgeWidth(4, 4));
    // Real theme colours, as hex, so Sigma can read them.
    expect(graph.getNodeAttribute("group:G01", "color")).toBe("#3987e5");
  });

  it("keeps groups in place when the week changes and swaps the ties", () => {
    const { rerender } = render(<SigmaNetwork {...props} />);
    const before = loaded().nodes().map((key) => loaded().getNodeAttributes(key));
    rerender(<SigmaNetwork {...props} week="2000-01-10" />);
    expect(loaded().nodes().map((key) => loaded().getNodeAttributes(key))).toEqual(before);
    expect(loaded().edges().map((key) => loaded().extremities(key))).toEqual([["group:G02", "group:G03"]]);
    expect(screen.getByRole("group")).toHaveAccessibleName("Group network for the week of 2000-01-10");
  });

  it("sizes items in layout units so points stay inside their disc at every zoom", () => {
    render(<SigmaNetwork {...props} />);
    expect(sigmaStub.settings.itemSizesReference).toBe("positions");
    expect(sigmaStub.settings.zoomToSizeRatioFunction?.(3)).toBe(3);
  });

  it("highlights a hovered group and its ties, dims the rest, and ignores hovered points", () => {
    render(<SigmaNetwork {...props} mode="individuals" />);
    const tie = loaded().edges()[0] ?? "";
    act(() => sigmaStub.handlers.enterNode?.({ node: "group:G03" }));
    expect(drawnNode("group:G03")).toMatchObject({ highlighted: true });
    expect(drawnNode("group:G01")).toMatchObject({ label: null });
    expect(drawnEdge(tie)).toMatchObject({ hidden: true });
    expect(screen.getByRole("status")).toHaveTextContent("Group G03 · 6 people · tied to 0 groups this week");
    act(() => sigmaStub.handlers.leaveNode?.({ node: "group:G03" }));
    expect(drawnNode("group:G01")).toMatchObject({ label: "G01" });
    expect(drawnEdge(tie)).not.toHaveProperty("hidden");
    // Hovering an anonymous point changes nothing and shows nothing.
    act(() => sigmaStub.handlers.enterNode?.({ node: pointKey(0, 0) }));
    expect(drawnNode("group:G01")).toMatchObject({ label: "G01" });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("searches groups by label, focuses the match and moves the camera to it", async () => {
    const user = userEvent.setup();
    render(<SigmaNetwork {...props} />);
    await user.type(screen.getByRole("combobox", { name: "Search a group by label" }), "g02{Enter}");
    expect(sigmaStub.gotoNode).toHaveBeenCalledWith("group:G02");
    expect(drawnNode("group:G02")).toMatchObject({ highlighted: true });
    expect(screen.getByRole("status")).toHaveTextContent("Group G02 · 9 people · tied to 1 group this week");
    await user.clear(screen.getByRole("combobox"));
    await user.type(screen.getByRole("combobox"), "point{Enter}");
    expect(screen.getByText("No group matches.")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("offers zoom, reset and fullscreen controls and a legend for size and weight", () => {
    render(<SigmaNetwork {...props} />);
    for (const name of ["Zoom in", "Zoom out", "Show the whole network", "Full screen"]) {
      expect(screen.getByTitle(name)).toBeInTheDocument();
    }
    const legend = screen.getByTestId("network-legend");
    expect(legend).toHaveTextContent("Circle area: people");
    expect(legend).toHaveTextContent("6");
    expect(legend).toHaveTextContent("14");
    expect(legend).toHaveTextContent("Line width: weekly weight");
    expect(legend).not.toHaveTextContent("anonymous person");
  });

  it("in the Individuals mode adds one anonymous point per person and says so in the legend", () => {
    render(<SigmaNetwork {...props} mode="individuals" />);
    const points = loaded().filterNodes((_, node) => node.kind === "point");
    expect(points).toHaveLength(14 + 9 + 6);
    expect(screen.getByTestId("network-legend")).toHaveTextContent("Each small dot: one anonymous person");
  });
});
