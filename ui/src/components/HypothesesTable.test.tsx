import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { View } from "@/App";
import { HELD_TRUE, HypothesesTable } from "@/components/HypothesesTable";
import { allHypotheses } from "@/lib/hypotheses";
import { exploratory, handBuilt } from "@/test/hypotheses";
import { sampleData } from "@/test/sample";

function renderTable(data = handBuilt()) {
  return render(<HypothesesTable entries={allHypotheses(data.hypotheses, data.exploratory, data.checks)} />);
}

/** The main rows, without the artifact-check detail lines. */
function mainRows(): HTMLElement[] {
  return screen.getAllByRole("row").filter((row) => row.hasAttribute("data-held-true"));
}

function rowFor(id: string): HTMLElement {
  const row = mainRows().find((r) => r.querySelector("td span")?.textContent === id);
  if (!row) throw new Error(`no row for ${id}`);
  return row;
}

describe("HypothesesTable", () => {
  it("shows one table of all hypotheses, H1 to H24, in order", () => {
    renderTable();
    expect(mainRows().map((row) => row.querySelector("td span")?.textContent)).toEqual(
      Array.from({ length: 24 }, (_, i) => `H${i + 1}`),
    );
    expect(screen.queryByText(/second family/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Exploratory hypotheses/)).not.toBeInTheDocument();
  });

  it("has the shared columns", () => {
    renderTable();
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual([
      "Hypothesis",
      "Claim / measure",
      "Predicted",
      "Effect or median change (95% interval)",
      "p (Holm)",
      "Robustness",
      "Outcome",
      "Stated",
    ]);
  });

  it("labels a hypothesis of the post-hoc family post hoc, like H26", () => {
    const { hypotheses, exploratory: rows, checks } = handBuilt();
    const entries = allHypotheses(hypotheses, [...rows, exploratory(25, { family: "post hoc" })], checks);
    render(<HypothesesTable entries={entries} />);
    expect(within(rowFor("H25")).getByText("post hoc")).toBeInTheDocument();
  });

  it("notes a passing placebo that already shows the crisis change", () => {
    const { hypotheses, exploratory: rows, checks } = handBuilt();
    // H21 as released: fell by 0.148; the placebo interval lies wholly below zero as well.
    const h21 = { median_change: -0.148, ci_low: -0.191, ci_high: -0.106, placebo_median: -0.139, placebo_ci_low: -0.257, placebo_ci_high: -0.0672 };
    const entries = allHypotheses(hypotheses, rows.map((row) => (row.hypothesis === "H21" ? { ...row, ...h21 } : row)), checks);
    render(<HypothesesTable entries={entries} />);
    expect(within(rowFor("H21")).getByText("the calm period already shows this change")).toBeInTheDocument();
    expect(screen.getAllByText("the calm period already shows this change")).toHaveLength(1);
  });

  it("states when each hypothesis was stated, from its table", () => {
    renderTable();
    expect(within(rowFor("H4")).getByText("pre-registered")).toBeInTheDocument();
    expect(within(rowFor("H5")).getByText("stated before computed, after earlier results")).toBeInTheDocument();
    expect(screen.getAllByText("pre-registered")).toHaveLength(4);
    expect(screen.getAllByText("stated before computed, after earlier results")).toHaveLength(20);
  });

  it("marks the headline and the confident hypothesis as held true, with the accent", () => {
    renderTable();
    expect(screen.getAllByText(HELD_TRUE)).toHaveLength(2);
    for (const id of ["H1", "H16"]) {
      expect(rowFor(id)).toHaveAttribute("data-held-true", "true");
      expect(within(rowFor(id)).getByText(HELD_TRUE)).toBeInTheDocument();
    }
    expect(rowFor("H2")).toHaveAttribute("data-held-true", "false");
    expect(within(rowFor("H16")).getByText("volume-equalised: 0.1 (0.06 to 0.17)")).toHaveClass("text-primary");
  });

  it("shows a pre-registered hypothesis with effect, Holm p, robustness and outcome", () => {
    renderTable();
    const h1 = within(rowFor("H1"));
    expect(h1.getByText("In-degree concentration (Gini), core network")).toBeInTheDocument();
    expect(h1.getByText("change week 2001-08-13")).toBeInTheDocument();
    expect(h1.getByText("1.8 (1.2 to 2.4)")).toBeInTheDocument();
    expect(h1.getByText("standardised effect")).toBeInTheDocument();
    expect(h1.getByText("0.008")).toBeInTheDocument();
    expect(h1.getByText("leave-one-out 0.1 to 0.4")).toBeInTheDocument();
    expect(h1.getByText("null model z 0.5")).toBeInTheDocument();
    expect(h1.getByText("variants 0/3")).toBeInTheDocument();
    expect(h1.getByText("supported: yes")).toBeInTheDocument();
    expect(h1.getByText("high confidence")).toBeInTheDocument();
    // The release does not carry the direction of H1–H4: shown as missing, never guessed.
    expect(h1.getByTitle(/not in the release data/)).toHaveTextContent("—");
  });

  it("shows a within-custodian hypothesis with its measure, direction, placebo and leave-one-out", () => {
    renderTable();
    const h16 = within(rowFor("H16"));
    expect(h16.getByText("measure 16")).toBeInTheDocument();
    expect(h16.getByText("30 custodians")).toBeInTheDocument();
    expect(h16.getByText("up")).toBeInTheDocument();
    expect(h16.getByText("0.25 (0.12 to 0.38)")).toBeInTheDocument();
    expect(h16.getByText("median change")).toBeInTheDocument();
    expect(h16.getByText("0.002")).toBeInTheDocument();
    expect(h16.getByText("placebo passes")).toBeInTheDocument();
    expect(h16.getByText("leave-one-out stable")).toBeInTheDocument();
    expect(h16.getByText("confident")).toBeInTheDocument();
    const h6 = within(rowFor("H6"));
    expect(h6.getByText("down")).toBeInTheDocument();
    expect(h6.getByText("timestamps are shifted in this window")).toBeInTheDocument();
    expect(h6.queryByText(/volume-equalised/)).not.toBeInTheDocument();
  });

  it("puts each artifact check under its hypothesis", () => {
    renderTable();
    const rows = screen.getAllByRole("row");
    const details = screen.getAllByTestId("artifact-check");
    expect(details).toHaveLength(2);
    expect(rows.indexOf(details[0] as HTMLElement)).toBe(rows.indexOf(rowFor("H2")) + 1);
    expect(rows.indexOf(details[1] as HTMLElement)).toBe(rows.indexOf(rowFor("H3")) + 1);
    expect(details[0]).toHaveTextContent(
      "Artifact check (baseline placebo): statistic 0.4, 95% interval [-0.3, 1.1], 26 units — passes. " +
        "out-of-sample jump within the calm baseline year is small",
    );
    expect(details[1]).toHaveTextContent("— fails. drift explains it");
  });

  it("writes suppressed counts and missing numbers as such, never as a failure", () => {
    const data = handBuilt();
    const suppressed = exploratory(5, {
      custodians: null,
      median_change: null,
      p_holm: null,
      outcome: null,
      loo_stable: null,
      placebo_passes: null,
    });
    renderTable({ ...data, exploratory: [suppressed] });
    const h5 = within(rowFor("H5"));
    expect(h5.getByText("custodians suppressed")).toBeInTheDocument();
    expect(h5.getByText("placebo suppressed")).toBeInTheDocument();
    expect(h5.getByText("leave-one-out suppressed")).toBeInTheDocument();
    expect(h5.getByText("suppressed")).toBeInTheDocument();
    expect(h5.queryByText(/fails|unstable/)).toBeNull();
    expect(h5.getAllByText("—").length).toBeGreaterThanOrEqual(2);
  });

  it("is the Hypotheses view's only table besides H26's own evidence, introduced with counts read from the data", () => {
    const data = sampleData();
    const rows = handBuilt();
    const tables = { ...data.tables, hypotheses: rows.hypotheses, exploratory: rows.exploratory, artifact_checks: rows.checks };
    const { container } = render(<View view="hypotheses" data={{ ...data, tables }} onSelect={() => undefined} />);
    const outsideDeparture = screen.getAllByRole("table").filter((table) => !table.closest("[data-testid='departure-details']"));
    expect(outsideDeparture).toHaveLength(1);
    expect(container).toHaveTextContent(
      "One list, ordered by number: 4 pre-registered (before any real data was analysed), 20 stated before computed, after earlier results, and 1 post hoc (after every other result was known, still before its own result was computed).",
    );
    expect(mainRows()).toHaveLength(25);
  });
});
