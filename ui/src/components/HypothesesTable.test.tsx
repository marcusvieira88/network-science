import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HypothesesTable } from "@/components/HypothesesTable";
import { sampleData } from "@/test/sample";

describe("HypothesesTable", () => {
  it("shows every hypothesis with p, Holm p, effect, interval, robustness and badges", () => {
    render(<HypothesesTable hypotheses={sampleData().tables.hypotheses} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(4);
    const [h1Row, , h3Row] = rows;
    if (!h1Row || !h3Row) throw new Error("rows missing");
    const h3 = within(h3Row);
    expect(h3.getByText("H3")).toBeInTheDocument();
    expect(h3.getByText("0.410")).toBeInTheDocument();
    expect(h3.getByText("0.820")).toBeInTheDocument();
    expect(h3.getByText("[-0.3, 0.5]")).toBeInTheDocument();
    expect(h3.getByText("0/3")).toBeInTheDocument();
    expect(h3.getByText("no")).toBeInTheDocument();
    expect(h3.getByText("low confidence")).toBeInTheDocument();
    expect(h3.getByText("none")).toBeInTheDocument();
    expect(within(h1Row).getByText("headline")).toBeInTheDocument();
  });

  it("shows a dash for an effect that could not be computed", () => {
    const [first] = sampleData().tables.hypotheses;
    if (!first) throw new Error("sample has no hypotheses");
    render(<HypothesesTable hypotheses={[{ ...first, effect: null, ci_low: null, ci_high: null }]} />);
    expect(screen.getAllByText("—")).toHaveLength(2);
  });
});
