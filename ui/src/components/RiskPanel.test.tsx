import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskPanel } from "@/components/RiskPanel";
import { reidByVariant } from "@/lib/risk";
import { sampleData } from "@/test/sample";

describe("RiskPanel", () => {
  const rows = sampleData().tables.risk;

  it("groups re-identification by release variant and attacker", () => {
    expect(reidByVariant(rows)).toEqual([
      { variant: "R0", A1: 0.9, A2: 0.62, A3: 0.7 },
      { variant: "R1", A1: 0, A2: 0, A3: 0 },
      { variant: "R2", A1: 0, A2: 0, A3: 0 },
    ]);
  });

  it("puts risk and utility for every variant and attacker side by side", () => {
    render(<RiskPanel rows={rows} />);
    const [table] = screen.getAllByRole("table");
    if (!table) throw new Error("table missing");
    expect(table.querySelectorAll("tbody tr")).toHaveLength(9);
    expect(table).toHaveTextContent("R0 · pseudonymised edge list (person-level, never published)");
    expect(table).toHaveTextContent("90%");
    expect(table).toHaveTextContent("0.97");
  });

  it("marks a zero on a release without person-level records as by construction, and only there", () => {
    render(<RiskPanel rows={rows} />);
    const [table] = screen.getAllByRole("table");
    if (!table) throw new Error("table missing");
    const marked = [...table.querySelectorAll("tbody tr")].filter((tr) => tr.textContent?.includes("0% (by construction)"));
    // The sample's six R1 and R2 rows are all zero; none of the three R0 rows is.
    expect(marked).toHaveLength(6);
    expect(marked.every((tr) => !tr.textContent?.startsWith("R0"))).toBe(true);
    expect(screen.getByText(/it is the only release these attacks measure/)).toBeInTheDocument();
  });

  it("says why utility is empty when there is no headline to recompute", () => {
    const { rerender } = render(<RiskPanel rows={rows} />);
    expect(screen.queryByText(/no headline finding to recompute/)).not.toBeInTheDocument();
    rerender(<RiskPanel rows={rows.map((row) => ({ ...row, utility_effect_ratio: null, finding_survives: null }))} />);
    expect(screen.getByText(/no headline finding to recompute/)).toBeInTheDocument();
  });

  it("shows whether the finding survives as yes, no or n/a", () => {
    const [first, second, third] = rows;
    if (!first || !second || !third) throw new Error("sample has fewer than three risk rows");
    render(
      <RiskPanel
        rows={[
          { ...first, finding_survives: null },
          { ...second, finding_survives: false },
          { ...third, finding_survives: true },
        ]}
      />,
    );
    const [table] = screen.getAllByRole("table");
    if (!table) throw new Error("table missing");
    const column = [...table.querySelectorAll("thead th")].findIndex((th) => th.textContent === "Finding survives");
    expect(column).toBeGreaterThanOrEqual(0);
    const cells = [...table.querySelectorAll("tbody tr")].map((tr) => tr.children[column]?.textContent);
    expect(cells).toEqual(["n/a", "no", "yes"]);
  });
});
