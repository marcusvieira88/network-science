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
      { variant: "R1", A1: 0, A2: 0.02, A3: 0 },
      { variant: "R2", A1: 0, A2: 0, A3: 0 },
    ]);
  });

  it("puts risk and utility for every variant and attacker side by side", () => {
    render(<RiskPanel rows={rows} />);
    const [table] = screen.getAllByRole("table");
    if (!table) throw new Error("table missing");
    expect(table.querySelectorAll("tbody tr")).toHaveLength(9);
    expect(table).toHaveTextContent("R0 · pseudonymised edge list (before)");
    expect(table).toHaveTextContent("90%");
    expect(table).toHaveTextContent("0.97");
  });
});
