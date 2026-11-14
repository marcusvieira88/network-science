import { describe, expect, it } from "vitest";

import { DataError } from "@/lib/data";
import {
  TIMING_LABELS,
  allHypotheses,
  countByKind,
  countByTiming,
  placeboShowsChange,
  timingOf,
  equalisedEstimate,
  formatEstimate,
  heldTrueLines,
  hypothesisNumber,
  releaseHypotheses,
  retentionCheck,
} from "@/lib/hypotheses";
import { withRealDepartures } from "@/test/departures";
import { check, exploratory, handBuilt, preregistered } from "@/test/hypotheses";
import { sampleData } from "@/test/sample";

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
    expect(countByKind(entries)).toEqual({ preregistered: 4, exploratory: 20, departure: 0 });
  });

  it("takes the kind from the table a row comes from, not from its id", () => {
    const entries = allHypotheses([preregistered("H2")], [exploratory(7, { hypothesis: "H7" }), exploratory(2, { hypothesis: "X2" })], []);
    expect(entries.map((e) => [e.id, e.kind, TIMING_LABELS[timingOf(e)]])).toEqual([
      ["H2", "preregistered", "pre-registered"],
      ["X2", "exploratory", "stated before computed, after earlier results"],
      ["H7", "exploratory", "stated before computed, after earlier results"],
    ]);
  });

  it("orders ids with another prefix (such as the dated record's E-numbers) by number too", () => {
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

describe("retentionCheck", () => {
  it("reports a failed retention check with its estimate, and nothing where none ran", () => {
    expect(retentionCheck(exploratory(16))).toBeNull();
    const failed = exploratory(16, {
      retention_passes: false,
      retention_median: 0.111,
      retention_ci_low: -0.111,
      retention_ci_high: 0.3,
    });
    expect(retentionCheck(failed)).toMatch(/^fails, /);
  });
});

describe("releaseHypotheses", () => {
  it("adds H26 after every other hypothesis, as its own kind", () => {
    const entries = releaseHypotheses(withRealDepartures(sampleData()));
    expect(entries).toHaveLength(26);
    const last = entries[entries.length - 1];
    expect([last?.id, last?.kind, last?.heldTrue]).toEqual(["H26", "departure", false]);
    expect(countByKind(entries)).toEqual({ preregistered: 4, exploratory: 21, departure: 1 });
  });

  it("holds H26 true only for an outcome of high or moderate confidence", () => {
    const held = releaseHypotheses(sampleData()).find((entry) => entry.kind === "departure");
    expect(held?.heldTrue).toBe(true);
  });

  it("labels H1–H4 pre-registered, H5–H24 stated before computed, and H25 and H26 post hoc", () => {
    const entries = releaseHypotheses(withRealDepartures(sampleData()));
    const label = (id: string) => entries.flatMap((entry) => (entry.id === id ? [TIMING_LABELS[timingOf(entry)]] : []));
    expect(label("H4")).toEqual(["pre-registered"]);
    expect(label("H5")).toEqual(["stated before computed, after earlier results"]);
    expect(label("H24")).toEqual(["stated before computed, after earlier results"]);
    expect(label("H25")).toEqual(["post hoc"]);
    expect(label("H26")).toEqual(["post hoc"]);
    expect(countByTiming(entries)).toEqual({ preregistered: 4, stated: 20, postHoc: 2 });
  });

  it("reads a passing placebo that already shows the crisis change", () => {
    // H21 as released: fell by 0.148 in the crisis; the placebo interval lies wholly below zero.
    const h21 = exploratory(21, { median_change: -0.148, placebo_median: -0.139, placebo_ci_low: -0.257, placebo_ci_high: -0.0672 });
    // H14 as released: fell by 0.168; the placebo rose and its interval includes zero.
    const h14 = exploratory(14, { median_change: -0.168, placebo_median: 0.0816, placebo_ci_low: -0.0279, placebo_ci_high: 0.105 });
    // H25 as released: rose by 0.00826; the placebo median is larger, its interval touches zero.
    const h25 = exploratory(25, { median_change: 0.00826, placebo_median: 0.0248, placebo_ci_low: 0, placebo_ci_high: 0.0331 });
    expect([h21, h14, h25].map(placeboShowsChange)).toEqual([true, false, true]);
    // H11 as released: predicted down, rose by 1.03; the placebo rose by 1.55, its interval including zero.
    const h11 = exploratory(11, { direction: "down", median_change: 1.03, placebo_median: 1.55, placebo_ci_low: -2.43, placebo_ci_high: 5.06 });
    expect(placeboShowsChange(h11)).toBe(false);
    expect(placeboShowsChange(exploratory(8, { median_change: 0 }))).toBe(false);
    expect(placeboShowsChange(exploratory(9, { placebo_median: null }))).toBe(false);
  });
});
