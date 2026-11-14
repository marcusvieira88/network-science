import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Overview } from "@/components/Overview";
import { handBuilt } from "@/test/hypotheses";
import { sampleData } from "@/test/sample";

function dataWith(rows = handBuilt()) {
  const data = sampleData();
  return {
    ...data,
    tables: { ...data.tables, hypotheses: rows.hypotheses, exploratory: rows.exploratory, artifact_checks: rows.checks },
  };
}

describe("Overview", () => {
  it("adds a Held true line under the finding card for each held-true measure", () => {
    render(<Overview data={dataWith()} />);
    expect(
      screen.getByText("Held true: H16 — measure 16, change 0.25 (0.12 to 0.38), volume-equalised 0.1 (0.06 to 0.17)"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Exploratory:/)).not.toBeInTheDocument();
  });

  it("adds no line when nothing is held true", () => {
    const rows = handBuilt();
    const exploratory = rows.exploratory.map((row) => ({ ...row, outcome: "inconclusive" as const }));
    render(<Overview data={dataWith({ ...rows, exploratory })} />);
    expect(screen.queryByText(/^Held true:/)).not.toBeInTheDocument();
  });
});
