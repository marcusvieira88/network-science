import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ExploratoryTable } from "@/components/ExploratoryTable";
import { sampleData } from "@/test/sample";

function rowFor(id: string): HTMLElement {
  const row = screen.getAllByRole("row").find((r) => within(r).queryByText(id, { exact: true }));
  if (!row) throw new Error(`no row for ${id}`);
  return row;
}

describe("ExploratoryTable", () => {
  it("states that the family is exploratory and Holm-corrected across all twenty", () => {
    render(<ExploratoryTable rows={sampleData().tables.exploratory} />);
    expect(
      screen.getByText("Exploratory hypotheses E1–E20 (stated before computing; Holm across all twenty)"),
    ).toBeInTheDocument();
    expect(screen.getByText(/exploratory, not pre-registered/)).toBeInTheDocument();
  });

  it("shows one row per hypothesis in order", () => {
    render(<ExploratoryTable rows={[...sampleData().tables.exploratory].reverse()} />);
    const ids = screen.getAllByRole("row").slice(1).map((r) => r.querySelector("td")?.textContent ?? "");
    expect(ids.map((text) => text.match(/^E\d+/)?.[0])).toEqual(Array.from({ length: 20 }, (_, i) => `E${i + 1}`));
  });

  it("shows the estimate, Holm p, placebo, leave-one-out, outcome and volume-equalised result", () => {
    render(<ExploratoryTable rows={sampleData().tables.exploratory} />);
    const e12 = within(rowFor("E12"));
    expect(e12.getByText("measure E12")).toBeInTheDocument();
    expect(e12.getByText("up")).toBeInTheDocument();
    expect(e12.getByText("32")).toBeInTheDocument();
    expect(e12.getByText("0.25 (0.12 to 0.38)")).toBeInTheDocument();
    expect(e12.getByText("0.002")).toBeInTheDocument();
    expect(e12.getByText("passes")).toBeInTheDocument();
    expect(e12.getByText("stable")).toBeInTheDocument();
    expect(e12.getByText("confident")).toBeInTheDocument();
    expect(e12.getByText("volume-equalised: 0.1 (0.06 to 0.17)")).toBeInTheDocument();
    expect(e12.getByText("second family")).toBeInTheDocument();
    expect(rowFor("E12")).toHaveAttribute("data-confident", "true");

    const e16 = within(rowFor("E16"));
    expect(e16.getByText("fails")).toBeInTheDocument();
    expect(e16.getByText("inconclusive")).toBeInTheDocument();
    expect(rowFor("E16")).toHaveAttribute("data-confident", "false");
  });

  it("shows caveats, the family tag only on E11–E20 and no equalised line where none was computed", () => {
    render(<ExploratoryTable rows={sampleData().tables.exploratory} />);
    const e1 = within(rowFor("E1"));
    expect(e1.getByText(/timestamps in the reference year of the corpus are shifted/)).toBeInTheDocument();
    expect(e1.queryByText(/volume-equalised/)).not.toBeInTheDocument();
    expect(e1.queryByText("second family")).not.toBeInTheDocument();
    expect(e1.getByText("up")).toBeInTheDocument();
    expect(within(rowFor("E7")).getByText("down")).toBeInTheDocument();
    expect(screen.getAllByText("second family")).toHaveLength(10);
  });

  it("writes suppressed custodian counts and missing numbers as such", () => {
    const [first] = sampleData().tables.exploratory;
    if (!first) throw new Error("sample has no exploratory rows");
    render(<ExploratoryTable rows={[{ ...first, custodians: null, median_change: null, p_holm: null }]} />);
    const e1 = within(rowFor("E1"));
    expect(e1.getByText("suppressed")).toBeInTheDocument();
    expect(e1.getAllByText("—").length).toBeGreaterThanOrEqual(2);
  });
});
