import { describe, expect, it } from "vitest";

import { DataError } from "@/lib/data";
import {
  STATED,
  allHypotheses,
  countByKind,
  equalisedEstimate,
  formatEstimate,
  heldTrueLines,
  hypothesisNumber,
} from "@/lib/hypotheses";
import { check, exploratory, handBuilt, preregistered } from "@/test/hypotheses";

function merged() {
  const { hypotheses, exploratory: rows, checks } = handBuilt();
  return allHypotheses(hypotheses, rows, checks);
}

describe("hypothesisNumber", () => {
  it("reads the number at the end of any id", () => {
    expect(hypothesisNumber("H1")).toBe(1);
    expect(hypothesisNumber("H24")).toBe(24);
    expect(hypothesisNumber("E12")).toBe(12);
  });

  it("refuses an id without a number", () => {
    expect(() => hypothesisNumber("Hx")).toThrow(DataError);
  });
});

describe("allHypotheses", () => {
  it("merges both tables into one list ordered by number, whatever order the rows come in", () => {
    const { hypotheses, exploratory: rows, checks } = handBuilt();
    const entries = allHypotheses([...hypotheses].reverse(), [...rows].reverse(), checks);
    expect(entries.map((e) => e.id)).toEqual(Array.from({ length: 24 }, (_, i) => `H${i + 1}`));
    expect(entries.map((e) => e.number)).toEqual(Array.from({ length: 24 }, (_, i) => i + 1));
    expect(countByKind(entries)).toEqual({ preregistered: 4, exploratory: 20 });
  });

  it("takes the kind from the table a row comes from, not from its id", () => {
    const entries = allHypotheses([preregistered("H2")], [exploratory(7, { hypothesis: "H7" }), exploratory(2, { hypothesis: "X2" })], []);
    expect(entries.map((e) => [e.id, e.kind, STATED[e.kind]])).toEqual([
      ["H2", "preregistered", "before any data"],
      ["X2", "exploratory", "before being computed"],
      ["H7", "exploratory", "before being computed"],
    ]);
  });

  it("orders the ids the committed sample still has (H1–H4 and E1–E20) by number too", () => {
    const entries = allHypotheses([preregistered("H1"), preregistered("H2")], [exploratory(2, { hypothesis: "E2" }), exploratory(1, { hypothesis: "E1" })], []);
    expect(entries.map((e) => e.id)).toEqual(["H1", "E1", "H2", "E2"]);
  });

  it("marks the headline and every confident outcome as held true, and nothing else", () => {
    expect(merged().filter((e) => e.heldTrue).map((e) => e.id)).toEqual(["H1", "H16"]);
  });

  it("attaches each artifact check to its hypothesis", () => {
    const entries = merged();
    const checksOf = (id: string) => {
      const entry = entries.find((e) => e.id === id);
      return entry?.kind === "preregistered" ? entry.checks.map((c) => c.check) : null;
    };
    expect(checksOf("H1")).toEqual([]);
    expect(checksOf("H2")).toEqual(["baseline_placebo"]);
    expect(checksOf("H3")).toEqual(["external_domain_drift"]);
    expect(checksOf("H5")).toBeNull();
  });
});

describe("formatEstimate", () => {
  it("writes a median with its interval in parentheses", () => {
    expect(formatEstimate(0.1, 0.06, 0.17)).toBe("0.1 (0.06 to 0.17)");
    expect(formatEstimate(-1.234, -2, 0.5)).toBe("-1.23 (-2 to 0.5)");
  });

  it("marks a missing median or bound as not computable", () => {
    expect(formatEstimate(null, 0.06, 0.17)).toBe("—");
    expect(formatEstimate(0.1, null, 0.17)).toBe("0.1 (—)");
  });

  it("gives no volume-equalised result where none was computed", () => {
    expect(equalisedEstimate(exploratory(5))).toBeNull();
    expect(equalisedEstimate(exploratory(5, { equalised_median: 0.1, equalised_ci_low: 0.06, equalised_ci_high: 0.17 }))).toBe(
      "0.1 (0.06 to 0.17)",
    );
  });
});

describe("heldTrueLines", () => {
  it("states each held-true measure with its change and volume-equalised change", () => {
    expect(heldTrueLines(merged())).toEqual([
      "Held true: H16 — measure 16, change 0.25 (0.12 to 0.38), volume-equalised 0.1 (0.06 to 0.17)",
    ]);
  });

  it("leaves out the volume-equalised part where there is none", () => {
    const entries = allHypotheses([], [exploratory(9, { measure: "late replies", outcome: "confident", median_change: 0.2, ci_low: 0.1, ci_high: 0.3 })], []);
    expect(heldTrueLines(entries)).toEqual(["Held true: H9 — late replies, change 0.2 (0.1 to 0.3)"]);
  });

  it("is empty when nothing is held true, and never repeats the headline card", () => {
    const entries = allHypotheses([preregistered("H1", { is_headline: true })], [exploratory(5, { outcome: "inconclusive" })], [check("H1")]);
    expect(heldTrueLines(entries)).toEqual([]);
  });
});
