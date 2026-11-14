import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CommunityGraph } from "@/components/CommunityGraph";
import type { SigmaNetworkProps } from "@/components/SigmaNetwork";
import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";

// The Sigma view draws the Groups mode but fails once the Overlap mode is chosen.
vi.mock("@/components/SigmaNetwork", () => ({
  default: ({ mode }: SigmaNetworkProps) => {
    if (mode === "overlap") throw new Error("WebGL context could not be created");
    return <div data-testid="sigma-view" data-mode={mode} />;
  },
}));

const groups: CommunityGroupRow[] = [
  { group: "G01", n_persons: 14 },
  { group: "G02", n_persons: 9 },
];
const edges: CommunityEdgeRow[] = [{ week: "2000-01-03", src_group: "G01", dst_group: "G02", weight: 4, n_messages: 10 }];

describe("CommunityGraph when the WebGL view fails in the Overlap mode", () => {
  it("falls back to the Groups mode, so no disabled tab stays selected", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const user = userEvent.setup();
    render(<CommunityGraph groups={groups} edges={edges} weeks={["2000-01-03"]} events={[]} minGroupSize={5} seed={1} baseline={null} webgl />);
    await screen.findByTestId("sigma-view");
    await user.click(screen.getByRole("tab", { name: "Overlap" }));
    expect(await screen.findAllByTestId("group-node")).toHaveLength(2);
    expect(screen.getByRole("tab", { name: "Overlap" })).toBeDisabled();
    expect(screen.getByRole("tab", { name: "Overlap" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tab", { name: "Groups" })).toHaveAttribute("aria-selected", "true");
  });
});
