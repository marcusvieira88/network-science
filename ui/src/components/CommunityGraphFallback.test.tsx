import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CommunityGraph } from "@/components/CommunityGraph";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";

// The 3D canvas fails to render (e.g. a WebGL context that cannot be created).
vi.mock("@/components/CommunityGraph3D", () => ({
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

describe("CommunityGraph when the 3D view fails", () => {
  it("falls back to the 2D network and switches the wording to circles", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { container } = render(
      <CommunityGraph groups={groups} edges={edges} weeks={["2000-01-03"]} events={[]} minGroupSize={5} seed={1} webgl />,
    );
    expect(await screen.findAllByTestId("group-node")).toHaveLength(2);
    expect(container).toHaveTextContent("Each circle is a group of at least 5 people, never an individual.");
    expect(container).toHaveTextContent("circle area follows group size");
    expect(container).not.toHaveTextContent("sphere");
  });
});
