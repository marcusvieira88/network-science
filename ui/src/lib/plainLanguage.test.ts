import { describe, expect, it } from "vitest";

import { allHypotheses } from "@/lib/hypotheses";
import { VERDICT_LABELS, executiveSummary, plainVerdict, weekInPlainWords } from "@/lib/plainLanguage";
import { check, exploratory, preregistered } from "@/test/hypotheses";

function verdictOf(...args: Parameters<typeof allHypotheses>) {
  const [entry] = allHypotheses(...args);
  if (!entry) throw new Error("no entry");
  return plainVerdict(entry);
}

describe("plainVerdict, hypotheses stated before any data", () => {
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

describe("plainVerdict, hypotheses stated before being computed", () => {
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

  it("names what held up", () => {
    const entries = allHypotheses([preregistered("H1", { is_headline: true, supported: "yes" })], [exploratory(5)], []);
    expect(executiveSummary(entries).answer).toBe("1 of 2 hypotheses held up: H1.");
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
