import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Overview } from "@/components/Overview";
import { sampleData } from "@/test/sample";

describe("Overview", () => {
  it("adds a line under the finding card for each confident exploratory hypothesis", () => {
    render(<Overview data={sampleData()} />);
    expect(
      screen.getByText("Exploratory: measure E12 — confident, volume-equalised change 0.1 (0.06 to 0.17)"),
    ).toBeInTheDocument();
  });

  it("adds no exploratory line when nothing there is confident", () => {
    const data = sampleData();
    const exploratory = data.tables.exploratory.map((row) => ({ ...row, outcome: "inconclusive" as const }));
    render(<Overview data={{ ...data, tables: { ...data.tables, exploratory } }} />);
    expect(screen.queryByText(/^Exploratory:/)).not.toBeInTheDocument();
  });
});
