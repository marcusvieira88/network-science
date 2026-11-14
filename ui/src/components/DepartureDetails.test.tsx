import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { View } from "@/App";
import { PlainHypotheses } from "@/components/PlainHypotheses";
import { type ReleaseData, parseRelease } from "@/lib/data";
import { releaseHypotheses } from "@/lib/hypotheses";
import { realPeriods, realTests } from "@/test/departures";
import { rawSample } from "@/test/sample";

/** The sample file with the real release's H26 tables, loaded through the same checks as release.json. */
function realShapedFile(): ReleaseData {
  const raw = rawSample();
  const tables = raw.tables as Record<string, unknown>;
  tables.departures = realPeriods();
  tables.departure_tests = realTests();
  return parseRelease(raw);
}

/** A published count cell: "fewer than k" or a whole number of at least k. */
const PUBLISHABLE_COUNT = /^(fewer than 5|([5-9]|[1-9]\d+))$/;

async function openDetails(): Promise<HTMLElement> {
  await userEvent.click(screen.getByText("Statement, windows, counts, tests and power"));
  return screen.getByTestId("departure-details");
}

describe("H26 in the Hypotheses view", () => {
  it("is in the plain list, unfolded, with its verdict, sentence and post-hoc label", () => {
    render(<PlainHypotheses entries={releaseHypotheses(realShapedFile())} />);
    const item = screen.getByText("H26").closest("li");
    if (!item) throw new Error("no H26 item");
    expect(item.closest("details")).toBeNull();
    expect(within(item).getByText("Not established")).toBeInTheDocument();
    expect(within(item).getByText("post hoc")).toBeInTheDocument();
    expect(item).toHaveTextContent("No wave of custodian departures in the crisis can be established");
  });

  it("shows the statement, windows, counts, test, variants and power", async () => {
    render(<PlainHypotheses entries={releaseHypotheses(realShapedFile())} />);
    const details = await openDetails();
    expect(details).toHaveTextContent("Stated post hoc: after every other result was known, still before its own result was computed.");
    expect(details).toHaveTextContent(/departs when they send nothing for 16 weeks/);
    expect(details).toHaveTextContent("fewer than 5 of 66 at risk in the crisis window");
    expect(details).toHaveTextContent("Of the 9 robustness variants in the rule, 2 keep the crisis share above the reference share");
    expect(details).toHaveTextContent(
      "at least 9 of the 66 custodians at risk would have had to depart in the crisis window for p below 0.05",
    );
    const [counts, variants] = within(details).getAllByRole("table");
    if (!counts || !variants) throw new Error("expected the counts and variants tables");
    const windows = within(counts).getAllByRole("row").slice(1);
    expect(windows.map((row) => row.querySelector("td")?.textContent)).toEqual([
      "crisis",
      "reference",
      "placebo after",
      "placebo before",
      "crisis before the split",
      "crisis from the split",
    ]);
    expect(within(variants).getAllByRole("row")).toHaveLength(realTests().length + 1);
  });

  it("never shows a count below 5: suppressed cells read 'fewer than 5'", async () => {
    render(<PlainHypotheses entries={releaseHypotheses(realShapedFile())} />);
    const details = await openDetails();
    const [counts] = within(details).getAllByRole("table");
    if (!counts) throw new Error("no counts table");
    const cells = within(counts)
      .getAllByRole("row")
      .slice(1)
      .flatMap((row) => Array.from(row.querySelectorAll("td")).slice(3, 6).map((cell) => cell.textContent ?? ""));
    expect(cells).toHaveLength(18);
    for (const cell of cells) expect(cell).toMatch(PUBLISHABLE_COUNT);
    expect(cells.filter((cell) => cell === "fewer than 5")).toHaveLength(12);
  });

  it("has a row in the analysts' table with its shares, p band and outcome", () => {
    const data = realShapedFile();
    render(<View view="hypotheses" data={data} onSelect={() => undefined} />);
    const row = screen.getAllByRole("row").find((item) => item.querySelector("td span")?.textContent === "H26");
    if (!row) throw new Error("no H26 row");
    expect(row).toHaveTextContent("crisis fewer than 5 of 66 at risk");
    expect(row).toHaveTextContent("p 0.05 or above");
    expect(row).toHaveTextContent("variants significant 0/9");
    expect(row).toHaveTextContent("not established");
  });
});
