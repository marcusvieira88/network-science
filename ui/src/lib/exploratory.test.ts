import { describe, expect, it } from "vitest";

import type { ExploratoryRow } from "@/lib/data";
import { exploratoryLeads, formatEstimate } from "@/lib/exploratory";
import { sampleData } from "@/test/sample";

function row(overrides: Partial<ExploratoryRow>): ExploratoryRow {
  const [first] = sampleData().tables.exploratory;
  if (!first) throw new Error("sample has no exploratory rows");
  return { ...first, ...overrides };
}

describe("formatEstimate", () => {
  it("writes a median with its interval in parentheses", () => {
    expect(formatEstimate(0.1, 0.06, 0.17)).toBe("0.1 (0.06 to 0.17)");
    expect(formatEstimate(-1.234, -2, 0.5)).toBe("-1.23 (-2 to 0.5)");
  });

  it("marks a missing median or bound as not computable", () => {
    expect(formatEstimate(null, 0.06, 0.17)).toBe("—");
    expect(formatEstimate(0.1, null, 0.17)).toBe("0.1 (—)");
  });
});

describe("exploratoryLeads", () => {
  it("states each confident hypothesis with its volume-equalised change, from the data", () => {
    expect(exploratoryLeads(sampleData().tables.exploratory)).toEqual([
      "Exploratory: measure E12 — confident, volume-equalised change 0.1 (0.06 to 0.17)",
    ]);
  });

  it("says when a confident row has no volume-equalised result", () => {
    const rows = [row({ measure: "late replies", outcome: "confident", equalised_median: null })];
    expect(exploratoryLeads(rows)).toEqual(["Exploratory: late replies — confident, volume-equalised change —"]);
  });

  it("is empty when nothing is confident", () => {
    expect(exploratoryLeads([row({ outcome: "inconclusive" }), row({ outcome: "not supported" })])).toEqual([]);
  });
});
