import { describe, expect, it } from "vitest";

import { allHypotheses, releaseHypotheses } from "@/lib/hypotheses";
import { VERDICT_LABELS, executiveSummary, plainVerdict, weekInPlainWords } from "@/lib/plainLanguage";
import { realTests, withRealDepartures } from "@/test/departures";
import { check, exploratory, preregistered } from "@/test/hypotheses";
import { sampleData } from "@/test/sample";

function verdictOf(...args: Parameters<typeof allHypotheses>) {
  const [entry] = allHypotheses(...args);
  if (!entry) throw new Error("no entry");
  return plainVerdict(entry);
}

describe("verdict labels", () => {
  it("are the eight labels the documents list", () => {
    expect(Object.values(VERDICT_LABELS)).toEqual([
      "Held up",
      "Explained by an artifact",
      "Not robust",
      "Unclear",
      "Could not be tested",
      "Changed the other way",
      "Not established",
      "Withheld",
    ]);
  });
});

describe("readings that cross-reference another result", () => {
  it("says an untestable hypothesis whose measure moved clearly is still used, as a measurement of the record", () => {
    const moved = exploratory(5, { caveat: "invalid: the hour convention changes", median_change: -0.44, ci_low: -0.51, ci_high: -0.37 });
    expect(verdictOf([], [moved], []).sentence).toBe(
      "Measure 5 could not be tested with this data: the hour convention changes. Its estimate is still used: as a measurement of the record, not of behaviour (see the main finding on the Executive summary).",
    );
    const flat = exploratory(7, { caveat: "untestable: every Bcc line repeats the Cc line", median_change: 0, ci_low: 0, ci_high: 0 });
    expect(verdictOf([], [flat], []).sentence).toBe("Measure 7 could not be tested with this data: every Bcc line repeats the Cc line.");
  });

  it("says when a result that moved the other way already did so before the crisis", () => {
    // H21 as released: predicted up, fell by 0.148; the placebo interval lies wholly below zero.
    const h21 = exploratory(21, { median_change: -0.148, ci_low: -0.191, ci_high: -0.106, placebo_median: -0.139, placebo_ci_low: -0.257, placebo_ci_high: -0.0672 });
    const verdict = verdictOf([], [h21], []);
    expect(verdict.verdict).toBe("opposite");
    expect(verdict.sentence).toBe(
      "Measure 21 did not go up as predicted: it went down (interval -0.19 to -0.11). The comparison before the crisis already shows the same move, so it did not start in the crisis window.",
    );
    // H14 as released: the placebo rose, with an interval that includes zero.
    const h14 = exploratory(14, { median_change: -0.168, ci_low: -0.272, ci_high: -0.102, placebo_median: 0.0816, placebo_ci_low: -0.0279, placebo_ci_high: 0.105 });
    expect(verdictOf([], [h14], []).sentence).toBe("Measure 14 did not go up as predicted: it went down (interval -0.27 to -0.1).");
  });
});

describe("plainVerdict, pre-registered hypotheses", () => {
  it("says a headline held up", () => {
    const verdict = verdictOf([preregistered("H1", { is_headline: true, supported: "yes", confidence: "high" })], [], []);
    expect(verdict.verdict).toBe("held");
    expect(verdict.sentence).toBe("In-degree concentration (Gini) in the core network changed, and the change held up under every check.");
  });

  it("says a supported one whose artifact check fails is explained by a known artifact of the data or the method, quoting the check", () => {
    const row = preregistered("H2", { supported: "yes", metric: "external_share", scope: "observed" });
    const verdict = verdictOf([row], [], [check("H2", { passes: false, note: "drift explains it" })]);
    expect(verdict.verdict).toBe("artifact");
    expect(verdict.sentence).toBe(
      "External share in the observed network looked like a real change, but a check showed a known artifact of the data or the method explains it: drift explains it.",
    );
  });

  it("says a supported one whose check could not run is not claimed", () => {
    const verdict = verdictOf([preregistered("H2", { supported: "yes" })], [], [check("H2", { passes: null })]);
    expect(verdict.verdict).toBe("weak");
    expect(verdict.sentence).toContain("the check for a known artifact could not run");
  });

  it("says a supported one that passes its check but is not the headline is not robust enough", () => {
    const verdict = verdictOf([preregistered("H2", { supported: "yes", confidence: "low" })], [], [check("H2")]);
    expect(verdict.verdict).toBe("weak");
    expect(verdict.sentence).toContain("not robust enough to claim (low confidence)");
  });

  it("says no reliable change and mixed evidence plainly", () => {
    expect(verdictOf([preregistered("H4")], [], []).verdict).toBe("none");
    expect(verdictOf([preregistered("H4", { supported: "inconclusive" })], [], []).verdict).toBe("unclear");
  });
});

describe("plainVerdict, within-custodian hypotheses", () => {
  it("says a confident outcome held up, in the predicted direction", () => {
    const verdict = verdictOf([], [exploratory(16, { outcome: "confident", direction: "down", measure: "weekend share" })], []);
    expect(verdict).toEqual({
      verdict: "held",
      label: VERDICT_LABELS.held,
      sentence: "Weekend share went down, as predicted, and the change held up under every check.",
    });
  });

  it("says an invalid or untestable one could not be tested, giving the reason", () => {
    const invalid = verdictOf([], [exploratory(5, { caveat: "invalid: timestamps are shifted" })], []);
    expect(invalid.verdict).toBe("untestable");
    expect(invalid.sentence).toBe("Measure 5 could not be tested with this data: timestamps are shifted.");
    expect(verdictOf([], [exploratory(7, { caveat: "untestable: Bcc repeats Cc" })], []).verdict).toBe("untestable");
  });

  it("keeps any other caveat on a not-supported or inconclusive one", () => {
    expect(verdictOf([], [exploratory(9)], []).sentence).toBe("No reliable change in measure 9.");
    const mixed = verdictOf([], [exploratory(16, { outcome: "inconclusive", caveat: "fails the retention check: x" })], []);
    expect(mixed.verdict).toBe("unclear");
    expect(mixed.sentence).toBe("The evidence on measure 16 is mixed (fails the retention check: x).");
  });

  it("says a not-supported one whose interval lies wholly on the other side changed the other way", () => {
    // Predicted up, interval -0.27 to -0.10: it went down (the real H14 shape).
    const down = verdictOf([], [exploratory(14, { direction: "up", ci_low: -0.27, ci_high: -0.1 })], []);
    expect(down.verdict).toBe("opposite");
    expect(down.sentence).toBe("Measure 14 did not go up as predicted: it went down (interval -0.27 to -0.1).");
    // Predicted down, interval 0.04 to 0.09: it went up (the real H22 shape).
    expect(verdictOf([], [exploratory(22, { direction: "down", ci_low: 0.04, ci_high: 0.09 })], []).verdict).toBe("opposite");
    // An interval that touches zero is no change either way.
    expect(verdictOf([], [exploratory(25, { direction: "up", ci_low: 0, ci_high: 0.03 })], []).verdict).toBe("none");
    expect(verdictOf([], [exploratory(9, { direction: "up", ci_low: -0.2, ci_high: 0.1 })], []).verdict).toBe("none");
  });

  it("says a suppressed outcome was withheld", () => {
    expect(verdictOf([], [exploratory(9, { outcome: null })], []).verdict).toBe("withheld");
  });
});

describe("executiveSummary", () => {
  it("answers in one line that nothing held up, and counts the rest by reason", () => {
    const entries = allHypotheses(
      [preregistered("H1"), preregistered("H2", { supported: "yes" })],
      [exploratory(5, { caveat: "invalid: shifted" }), exploratory(6), exploratory(7, { outcome: "inconclusive" })],
      [check("H2", { passes: false })],
    );
    expect(executiveSummary(entries)).toEqual({
      answer: "None of the 5 hypotheses held up under the checks.",
      points: [
        "1 looked real at first but is explained by a known artifact of the data or the method (H2).",
        "1 gave mixed evidence (H7).",
        "1 could not be tested with this data (H5).",
        "2 showed no reliable change.",
      ],
    });
  });

  it("lists the ones that changed the other way by id", () => {
    const entries = allHypotheses([], [exploratory(14, { ci_low: -0.27, ci_high: -0.1 }), exploratory(9)], []);
    expect(executiveSummary(entries).points).toEqual([
      "1 changed the opposite way to the prediction (H14).",
      "1 showed no reliable change.",
    ]);
  });

  it("names what held up", () => {
    const entries = allHypotheses([preregistered("H1", { is_headline: true, supported: "yes" })], [exploratory(5)], []);
    expect(executiveSummary(entries).answer).toBe("1 of 2 hypotheses held up: H1.");
  });
});

describe("H26 in plain words", () => {
  function departureVerdict(data = withRealDepartures(sampleData())) {
    const entry = releaseHypotheses(data).find((item) => item.kind === "departure");
    if (!entry) throw new Error("no H26 entry");
    return plainVerdict(entry);
  }

  it("reads the real outcome as no reliable change, with its reasons", () => {
    const verdict = departureVerdict();
    expect(verdict.verdict).toBe("none");
    expect(verdict.sentence).toMatch(/^No wave of custodian departures in the crisis can be established: fewer than 5 custodians departed/);
  });

  it("reads high or moderate as held up, and low as not robust", () => {
    expect(departureVerdict(sampleData()).verdict).toBe("held");
    const data = withRealDepartures(sampleData());
    const departure_tests = realTests().map((row) => (row.variant === "primary" ? { ...row, outcome: "low" as const } : row));
    expect(departureVerdict({ ...data, tables: { ...data.tables, departure_tests } }).verdict).toBe("weak");
  });

  it("counts 26 hypotheses and adds one sentence on structure, keeping H26 out of the other reasons", () => {
    // The sample's H1 holds up, so H26's sentence does not say "either".
    const summary = executiveSummary(releaseHypotheses(withRealDepartures(sampleData())));
    expect(summary.answer).toBe("1 of 26 hypotheses held up: H1.");
    expect(summary.points.filter((point) => point.includes("H26"))).toEqual([
      "No structural change can be established: H26 asked whether custodians left during the crisis, and no wave of " +
        "departures can be established; the test could only have seen a large wave (at least 9 of the 66 custodians at risk), " +
        "so a smaller one is not ruled out.",
    ]);
    expect(summary.points[summary.points.length - 1]).toContain("H26");
  });
});

describe("weekInPlainWords", () => {
  it("names the busiest link between real groups and how many pairs of real groups there were", () => {
    const ties = [
      { a: "G06", b: "other", weightAB: 2, weightBA: 1, total: 3 },
      { a: "G01", b: "G02", weightAB: 1, weightBA: 0, total: 1 },
      { a: "G03", b: "G04", weightAB: 0.5, weightBA: 0, total: 0.5 },
    ];
    // The outside bucket is not a group: it is never named as the busiest link or counted as a pair.
    expect(weekInPlainWords("2001-10-22", ties)).toBe(
      "In the week of 2001-10-22 the busiest link between groups was G01 ↔ G02 (weight 1); 2 pairs of groups exchanged mail.",
    );
  });

  it("says no mail ran between groups when the only ties are to the outside bucket", () => {
    const ties = [{ a: "G06", b: "other", weightAB: 2, weightBA: 1, total: 3 }];
    expect(weekInPlainWords("2001-10-22", ties)).toBe("In the week of 2001-10-22 no published mail ran between groups.");
  });

  it("says so when a week has no published link", () => {
    expect(weekInPlainWords("2001-10-22", [])).toBe("In the week of 2001-10-22 no published mail ran between groups.");
    expect(weekInPlainWords(null, [])).toBe("No week selected.");
  });
});
