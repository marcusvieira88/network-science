import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CommunityGraph } from "@/components/CommunityGraph";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";

// The Sigma view fails to render (e.g. a WebGL context that cannot be created).
vi.mock("@/components/SigmaNetwork", () => ({
  default: () => {
    throw new Error("WebGL context could not be created");
  },
}));

const groups: CommunityGroupRow[] = [
  { group: "G01", n_persons: 14 },
  { group: "G02", n_persons: 9 },
];
const edges: CommunityEdgeRow[] = [
  { week: "2000-01-03", src_group: "G01", dst_group: "G02", weight: 4, n_messages: 10 },
];

describe("CommunityGraph when the WebGL view fails", () => {
  it("falls back to the SVG network with the same explanation", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { container } = render(
      <CommunityGraph groups={groups} edges={edges} weeks={["2000-01-03"]} events={[]} minGroupSize={5} seed={1} baseline={null} webgl />,
    );
    expect(await screen.findAllByTestId("group-node")).toHaveLength(2);
    expect(container).toHaveTextContent("Each circle is a group of at least 5 people, never an individual.");
    expect(container).toHaveTextContent("circle area follows group size");
    expect(screen.getByRole("img")).toHaveAccessibleName("Group network for the week of 2000-01-03");
  });

  it("does not offer the Overlap mode in the SVG network, and says so", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<CommunityGraph groups={groups} edges={edges} weeks={["2000-01-03"]} events={[]} minGroupSize={5} seed={1} baseline={null} webgl />);
    await screen.findAllByTestId("group-node");
    expect(screen.getByRole("tab", { name: "Overlap" })).toBeDisabled();
    expect(screen.getByText(/The Overlap mode needs WebGL/)).toBeInTheDocument();
  });
});
