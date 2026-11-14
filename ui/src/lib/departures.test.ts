import { describe, expect, it } from "vitest";

import { DataError } from "@/lib/data";
import {
  countText,
  departureFrom,
  departureReasons,
  departureStatement,
  departureVerdictSentence,
  evidenceSentence,
  pText,
  powerSentence,
  rollingSentence,
  splitSentence,
  structureSentence,
  variantSentence,
} from "@/lib/departures";
import { realTests, withRealDepartures } from "@/test/departures";
import { sampleData } from "@/test/sample";

/** H26 is stated after H1–H25, so it is the twenty-sixth. */
const STATED = 26;

function real() {
  const data = withRealDepartures(sampleData());
  return departureFrom(data, STATED);
}

function sample() {
  return departureFrom(sampleData(), STATED);
}

describe("H26 read from the release", () => {
  it("takes the next number after every other hypothesis", () => {
    expect(real().id).toBe("H26");
  });

  it("reads a suppressed count as fewer than k, never as a number", () => {
    expect(countText(null, 5)).toBe("fewer than 5");
    expect(countText(66, 5)).toBe("66");
  });

  it("shows a p-value only where it is published, otherwise its band", () => {
    const { settings } = real();
    expect(pText(0.0011, "below alpha", settings)).toBe("p = 0.0011");
    expect(pText(null, "below alpha", settings)).toBe("p below 0.05");
    expect(pText(null, "below the family bound", settings)).toBe("p below 0.05/26");
    expect(pText(null, "alpha or above", settings)).toBe("p 0.05 or above");
    expect(pText(null, null, settings)).toBe("not published");
  });

  it("states the definition from the run parameters", () => {
    expect(departureStatement(real().settings)).toBe(
      "A custodian at risk at a window's start (sending and receiving in at least 4 of the 16 weeks before, and not already silent) " +
        "departs when they send nothing for 16 weeks while, in at least 4 of those weeks, their own mailbox receives mail that only it can hold. " +
        "If that mail stops too, the silence is a record end: the mailbox was no longer collected, which is not a departure.",
    );
  });

  it("gives the real evidence with every small count suppressed", () => {
    expect(evidenceSentence(real())).toBe(
      "Custodians who stopped sending for 16 weeks or more while their own mailbox kept receiving mail: fewer than 5 of 66 at risk " +
        "in the crisis window, against fewer than 5 of 26 at risk in the same weeks a year earlier (one-sided Fisher p 0.05 or above). " +
        "Record ends: fewer than 5 in the crisis window, fewer than 5 in the reference window.",
    );
  });

  it("gives the published share where the count reaches k", () => {
    expect(evidenceSentence(sample())).toContain("12 of 40 at risk (share 0.3) in the crisis window");
  });

  it("lists every failed condition of the rule, in the rule's order", () => {
    expect(departureReasons(real())).toEqual([
      "fewer than 5 custodians departed in the crisis window",
      "the crisis share is not significantly above the same weeks a year earlier (p 0.05 or above)",
      "an earlier window of the same length had at least as high a share",
    ]);
    expect(departureReasons(sample())).toEqual([]);
  });

  it("reads the real outcome in plain words", () => {
    expect(departureVerdictSentence(real())).toBe(
      "No wave of custodian departures in the crisis can be established: fewer than 5 custodians departed in the crisis window; " +
        "the crisis share is not significantly above the same weeks a year earlier (p 0.05 or above); " +
        "an earlier window of the same length had at least as high a share.",
    );
  });

  it("reads a passed rule with its confidence", () => {
    expect(departureVerdictSentence(sample())).toBe(
      "Custodians stopped sending while their mailbox kept receiving mail at a higher rate in the crisis than in the same weeks " +
        "a year earlier and than in any comparable earlier window (confidence: moderate).",
    );
  });

  it("states the rolling windows, the placebo and leave-one-out", () => {
    expect(rollingSentence(real())).toBe(
      "The crisis share is not above every one of the 55 earlier windows of the same length with at least 20 custodians at risk; " +
        "the pre-crisis placebo has p 0.05 or above; leave-one-out does not apply, since the test itself does not pass.",
    );
  });

  it("counts the robustness variants in the rule, and the one outside it", () => {
    expect(variantSentence(real())).toBe(
      "Of the 9 robustness variants in the rule, 2 keep the crisis share above the reference share and 0 keep p below 0.05; " +
        "1 publishes no comparison, because a window has too few custodians at risk. Counting every silence, record ends included " +
        "(variant any silence), the crisis share is still not significantly above a year earlier.",
    );
  });

  it("states the power: how large a wave the test could see", () => {
    expect(powerSentence(real())).toBe(
      "Even with no departure a year earlier, at least 9 of the 66 custodians at risk would have had to depart in the crisis window " +
        "for p below 0.05, so the test could see only a large wave; the placebo would have needed 16 of 51, so its passing shows little.",
    );
  });

  it("publishes the crisis split only when both parts reach k", () => {
    expect(splitSentence(real())).toBe(
      "Split at 2001-10-16 (Third-quarter loss announced), at least one part holds fewer than 5 departures, so neither is published.",
    );
    expect(splitSentence(sample())).toBe(
      "Of the crisis departures, 7 began before 2001-10-16 (Third-quarter loss announced) and 5 from then on.",
    );
  });

  it("sums the result up as the structure question, with what the test could not rule out", () => {
    expect(structureSentence(real(), true)).toBe(
      "No structural change can be established either: H26 asked whether custodians left during the crisis, and no wave of " +
        "departures can be established; the test could only have seen a large wave (at least 9 of the 66 custodians at risk), " +
        "so a smaller one is not ruled out.",
    );
    expect(structureSentence(sample(), false)).toBe(
      "H26: custodians stopped sending while their mailbox kept receiving mail at a higher rate in the crisis than a year earlier (confidence: moderate).",
    );
  });

  it("fails loudly when a run parameter it states is missing", () => {
    const data = withRealDepartures(sampleData());
    const parameters = { ...data.run.parameters, departure_silence_weeks: undefined };
    expect(() => departureFrom({ ...data, run: { ...data.run, parameters } }, STATED)).toThrow(DataError);
  });

  it("uses only the published primary row for the outcome", () => {
    expect(real().primary).toEqual(realTests()[0]);
  });
});
