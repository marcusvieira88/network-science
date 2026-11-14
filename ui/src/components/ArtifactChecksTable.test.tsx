import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ArtifactChecksTable } from "@/components/ArtifactChecksTable";
import { sampleData } from "@/test/sample";

describe("ArtifactChecksTable", () => {
  it("shows every artifact check with its result", () => {
    render(<ArtifactChecksTable checks={sampleData().tables.artifact_checks} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    const [h2Row, h3Row] = rows;
    if (!h2Row || !h3Row) throw new Error("rows missing");
    expect(within(h2Row).getByText("baseline placebo")).toBeInTheDocument();
    expect(within(h2Row).getByText("passes")).toBeInTheDocument();
    expect(within(h3Row).getByText("[-0.08, -0.02]")).toBeInTheDocument();
  });

  it("keeps a check that could not run visible as 'not run'", () => {
    const [first] = sampleData().tables.artifact_checks;
    if (!first) throw new Error("sample has no checks");
    render(
      <ArtifactChecksTable
        checks={[{ ...first, passes: null, statistic: null, ci_low: null, ci_high: null, n_units: null }]}
      />,
    );
    expect(screen.getByText("not run")).toBeInTheDocument();
  });
});
