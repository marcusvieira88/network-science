import { describe, expect, it } from "vitest";

import type { ReleaseData } from "@/lib/data";
import {
  confidenceCard,
  foundCard,
  funnelHeadline,
  headerHeadline,
  joinList,
  metricCaption,
  metricHeadline,
  privacyCard,
  qualityCard,
  recordCard,
  riskHeadline,
  studiedCard,
  summaryCards,
  whatItMeans,
} from "@/lib/executive";
import { worstReidentification } from "@/lib/risk";
import { metricSeries } from "@/lib/series";
import { sampleData } from "@/test/sample";

/**
 * The sample reshaped to the real release's outcomes (values copied from release/*.csv): no
 * headline, H2 and H3 fail their artifact checks, H5's shift lies far from zero, and the published
 * release R1 re-identifies nobody.
 */
function realShaped(): ReleaseData {
  const data = sampleData();
  const { tables } = data;
  const hypotheses = tables.hypotheses.map((row) =>
    row.hypothesis === "H1" ? { ...row, supported: "no" as const, confidence: "low" as const, is_headline: false } : { ...row, confidence: "low" as const },
  ).map((row) => (row.hypothesis === "H3" ? { ...row, supported: "yes" as const } : row))
    .map((row) => (row.hypothesis === "H4" ? { ...row, supported: "no" as const } : row));
  const artifact_checks = tables.artifact_checks.map((row) => ({ ...row, passes: false }));
  const exploratory = tables.exploratory.map((row) =>
    row.hypothesis === "H5"
      ? { ...row, measure: "after-hours share of sent messages (weekdays)", median_change: -0.4403, ci_low: -0.5122, ci_high: -0.3718 }
      : row.hypothesis === "H16"
        ? { ...row, measure: "share of sent-to contacts who also wrote to the custodian", median_change: 0.2665, ci_low: 0.1439, ci_high: 0.3856 }
        : row,
  );
  const risk = tables.risk.map((row) => {
    if (row.release_variant !== "R0") return { ...row, reid_top1: 0 };
    const real = { A1: [0.251, 12641], A2: [0.591, 12638], A3: [0.574, 12519] } as const;
    const [reid, targets] = real[row.attacker];
    return { ...row, reid_top1: reid, n_targets: targets };
  });
  const data_quality = [
    { order: 1, step: "files parsed", count_in: 517401, count_out: 517364, removed: 37, rule: null, precision: null, recall: null, precision_ci_low: null, precision_ci_high: null },
    { order: 2, step: "deduplicate", count_in: 517364, count_out: 250537, removed: 266827, rule: "exact+subset", precision: null, recall: null, precision_ci_low: null, precision_ci_high: null },
    { order: 3, step: "resolve identities", count_in: 85388, count_out: 84759, removed: 629, rule: "N1-N4", precision: null, recall: null, precision_ci_low: null, precision_ci_high: null },
    { order: 4, step: "manual merge check", count_in: 50, count_out: 50, removed: 0, rule: "seeded sample, judged by a person", precision: 1, recall: null, precision_ci_low: 0.929, precision_ci_high: 1 },
    { order: 15, step: "events in the network", count_in: 1328123, count_out: 823488, removed: 504635, rule: "sender-recipient events", precision: null, recall: null, precision_ci_low: null, precision_ci_high: null },
  ];
  return {
    ...data,
    run: { ...data.run, sample: false },
    tables: { ...tables, hypotheses, artifact_checks, exploratory, risk, data_quality },
  };
}

describe("joinList", () => {
  it("joins one, two and more items in plain English", () => {
    expect(joinList(["H2"])).toBe("H2");
    expect(joinList(["H2", "H3"])).toBe("H2 and H3");
    expect(joinList(["H2", "H3", "H5"])).toBe("H2, H3 and H5");
  });
});

describe("summary cards on the sample", () => {
  const data = sampleData();

  it("says what was studied", () => {
    expect(studiedCard(data)).toEqual({
      key: "studied",
      eyebrow: "What was studied",
      title: "Who emailed whom, and when, never what was written",
      points: [
        "2,721 distinct messages from the synthetic sample corpus, over 118 weeks (weeks of 1999-12-27 to 2002-03-25).",
        "Only each message's envelope was used: sender, recipients and time. Subject and X-Folder count as content and were never stored; bodies and attachments were never read.",
        "25 hypotheses about how communication changed around 5 public events (2001-08-14 to 2001-12-02), each written down before its result was computed.",
      ],
      view: "quality",
      linkLabel: "How the data was cleaned",
    });
  });

  it("says what was found, with the reasons", () => {
    const card = foundCard(data);
    expect(card.title).toBe("1 of 25 hypotheses held up: H1.");
    expect(card.points).toEqual([
      "1 looked real but is not robust enough to claim (H2).",
      "3 gave mixed evidence (H4, H16, H20).",
      "2 could not be tested with this data (H5, H7).",
      "18 showed no reliable change.",
    ]);
    expect(card.view).toBe("hypotheses");
  });

  it("names the questions the record could not answer, without a shift where the interval holds zero", () => {
    const card = recordCard(data);
    expect(card.title).toBe("Some results reflect how the data was kept");
    expect(card.points).toEqual([
      "H5: Measure H5 could not be tested with this data: timestamps in the reference year of the corpus are shifted by several hours.",
      "H7: Measure H7 could not be tested with this data: every Bcc line in the corpus repeats the Cc line.",
    ]);
  });

  it("says how sure we are", () => {
    expect(confidenceCard(data).points).toEqual([
      "Each result had to survive a correction for testing many hypotheses at once, repeats that leave out one mailbox at a time, and checks against known quirks of the data.",
      "Confidence of the 4 hypotheses stated before any data: 1 high, 1 moderate, 2 low.",
      "H16, measure H16, rose by a median of 0.25 (interval 0.12 to 0.38), but the change is not established once how much inbox mail was kept is accounted for.",
    ]);
    expect(confidenceCard(data).view).toBe("limits");
  });

  it("compares the person-level and the published release", () => {
    const card = privacyCard(data);
    expect(card.title).toBe("Pseudonymised is not anonymous");
    expect(card.points).toEqual([
      "From person-level data under pseudonyms (R0), the strongest of 3 simulated attackers re-identified 90% of 50 people.",
      "From the published release (R1), which holds only groups of at least 5 people, the strongest re-identified 2%.",
      "No attack on the published group tables themselves was run.",
    ]);
    expect(card.view).toBe("risk");
  });

  it("gives the cleaning numbers", () => {
    expect(qualityCard(data).points).toEqual([
      "6,731 of 6,731 files could be read.",
      "Removing 4,010 stored copies left 2,721 distinct messages.",
      "97 addresses were merged into 75 identities by documented rules; against known answers, precision is 100% and recall 100%.",
      "4,825 of 5,968 sender–recipient links entered the network; the rest belong to messages flagged out of it, such as mass mailings.",
    ]);
  });

  it("gives six cards, each leading to its evidence", () => {
    const cards = summaryCards(data);
    expect(cards.map((card) => card.key)).toEqual(["studied", "found", "record", "confidence", "privacy", "quality"]);
    expect(cards.map((card) => card.view)).toEqual(["quality", "hypotheses", "hypotheses", "limits", "risk", "quality"]);
  });

  it("says what it means for an organisation", () => {
    expect(whatItMeans(data)).toEqual([
      "Check how the data was kept before reading behaviour into it: here 2 of 25 results trace back to how the data was collected or analysed (H5, H7).",
      "Fix the questions and checks before looking at results, and publish every outcome: all 25 hypotheses are published here, including the 24 that did not hold up.",
      "Treat pseudonymised person-level data as identifiable: a simulated attacker re-identified 90% of people from it here. Share only groups of at least 5 people.",
      "This kind of question can be studied without reading content: only sender, recipients and time were used, and Subject and X-Folder were never stored.",
      "Before applying this to your own staff's email: collect header fields only at the source, keep the pseudonymisation key in your own key store, replace the noise sketch with a formal privacy budget, and agree the questions and thresholds with employee representatives, such as a works council, first.",
    ]);
  });
});

describe("summary cards on the real outcomes", () => {
  const data = realShaped();

  it("answers that nothing held up", () => {
    const card = foundCard(data);
    expect(card.title).toBe("None of the 25 hypotheses held up under the checks.");
    expect(card.points).toEqual([
      "2 looked real at first but are explained by quirks of the data (H2, H3).",
      "2 gave mixed evidence (H16, H20).",
      "2 could not be tested with this data (H5, H7).",
      "19 showed no reliable change.",
    ]);
  });

  it("leads with the change in the record", () => {
    const card = recordCard(data);
    expect(card.title).toBe("What changed was the record, not behaviour");
    expect(card.points).toEqual([
      "H5, after-hours share of sent messages (weekdays): within the same 32 custodians it moved by a median of -0.44 (interval -0.51 to -0.37) between the reference weeks (2000-08-14 to 2000-12-02) and the crisis weeks (2001-08-14 to 2001-12-02). It is not read as behaviour: timestamps in the reference year of the corpus are shifted by several hours.",
      "H2 and H3 passed their planned statistical tests, but checks show that how the data was collected explains them, not a change in how people communicated.",
      "H7: Measure H7 could not be tested with this data: every Bcc line in the corpus repeats the Cc line.",
      "Every within-custodian comparison (H5–H25) uses these same two windows, so each one compares two ways of keeping the record.",
    ]);
  });

  it("states the placebo limit when the record changed", () => {
    expect(confidenceCard(data).points).toEqual([
      "Each result had to survive a correction for testing many hypotheses at once, repeats that leave out one mailbox at a time, and checks against known quirks of the data.",
      "Confidence of the 4 hypotheses stated before any data: 4 low.",
      "H16, share of sent-to contacts who also wrote to the custodian, rose by a median of 0.27 (interval 0.14 to 0.39), but the change is not established once how much inbox mail was kept is accounted for.",
      "The calm-period placebo tests lie before the change in the record, so they cannot detect it.",
    ]);
  });

  it("explains that the published zero restates the design", () => {
    expect(privacyCard(data).points).toEqual([
      "From person-level data under pseudonyms (R0), the strongest of 3 simulated attackers re-identified 59.1% of 12,638 people.",
      "From the published release (R1), which holds only groups of at least 5 people, the strongest re-identified 0%.",
      "That zero follows from the design: the published tables hold no person-level records for an attack to match, so it is not a measurement of every remaining risk.",
      "No attack on the published group tables themselves was run.",
    ]);
  });

  it("gives the real cleaning numbers and the manual merge check", () => {
    expect(qualityCard(data).points).toEqual([
      "517,364 of 517,401 files could be read.",
      "Removing 266,827 stored copies left 250,537 distinct messages.",
      "85,388 addresses were merged into 84,759 identities by documented rules.",
      "A person checked 50 sampled merges and judged 100% of them correct (interval 92.9% to 100%).",
      "823,488 of 1,328,123 sender–recipient links entered the network; the rest belong to messages flagged out of it, such as mass mailings.",
    ]);
    expect(studiedCard(data).points[0]).toBe(
      "250,537 distinct messages from the public Enron email archive, over 118 weeks (weeks of 1999-12-27 to 2002-03-25).",
    );
  });

  it("frames the lessons on the real outcomes", () => {
    const [record, publish, privacy] = whatItMeans(data);
    expect(record).toBe(
      "Check how the data was kept before reading behaviour into it: here 4 of 25 results trace back to how the data was collected or analysed (H2, H3, H5, H7).",
    );
    expect(publish).toBe(
      "Fix the questions and checks before looking at results, and publish every outcome: all 25 hypotheses are published here, though none held up.",
    );
    expect(privacy).toBe(
      "Treat pseudonymised person-level data as identifiable: a simulated attacker re-identified 59.1% of people from it here. Share only groups of at least 5 people.",
    );
  });
});

describe("chart headlines", () => {
  const data = sampleData();

  it("names the peak week of the selected series", () => {
    const series = metricSeries(data.tables.weekly_metrics, { metric: "volume", scope: "core", variant: "default" });
    expect(metricHeadline(series, "volume", "core")).toBe("Message volume between custodians peaked in the week of 2002-01-07 at 133.17.");
    const observed = metricSeries(data.tables.weekly_metrics, { metric: "volume", scope: "observed", variant: "default" });
    expect(metricHeadline(observed, "volume", "observed")).toBe("Message volume in the observed network peaked in the week of 2001-04-23 at 135.49.");
  });

  it("takes the earliest of equal peaks and skips hidden weeks", () => {
    const series = [
      { week: "2001-01-01", value: null },
      { week: "2001-01-08", value: 3 },
      { week: "2001-01-15", value: 3 },
    ];
    expect(metricHeadline(series, "density", "core")).toBe("Density between custodians peaked in the week of 2001-01-08 at 3.");
    expect(metricHeadline([{ week: "2001-01-01", value: null }], "density", "core")).toBe(
      "Density between custodians: every week of this selection is hidden.",
    );
  });

  it("says how to read the metric chart", () => {
    expect(metricCaption({ start: "2000-01-01", end: "2000-12-31" })).toBe(
      "Each point is one week. The shaded band is the baseline period, 2000-01-01 to 2000-12-31; numbered dashed lines mark the public events listed below; gaps are weeks hidden because too few people were active to publish them. The archive kept more mail in some periods than in others, so a rise can reflect what was kept, not only how much people wrote.",
    );
    expect(metricCaption(null)).toBe(
      "Each point is one week. Numbered dashed lines mark the public events listed below; gaps are weeks hidden because too few people were active to publish them. The archive kept more mail in some periods than in others, so a rise can reflect what was kept, not only how much people wrote.",
    );
  });

  it("compares the releases in the risk headline", () => {
    expect(riskHeadline(data.tables.risk)).toBe(
      "The strongest attacker re-identified 90% of people from person-level data (R0) and 2% from the published release (R1).",
    );
    expect(riskHeadline(realShaped().tables.risk)).toBe(
      "The strongest attacker re-identified 59.1% of people from person-level data (R0) and 0% from the published release (R1). That zero follows from the design: the published tables hold no person-level records for an attack to match.",
    );
    expect(riskHeadline([])).toBeNull();
  });

  it("finds the strongest attack per release", () => {
    expect(worstReidentification(data.tables.risk, "R0")).toEqual({ rate: 0.9, targets: 50 });
    expect(worstReidentification(data.tables.risk, "R1")).toEqual({ rate: 0.02, targets: 50 });
    expect(worstReidentification([], "R1")).toBeNull();
  });

  it("sums up the cleaning funnel and the header ruling", () => {
    expect(funnelHeadline(data.tables.data_quality)).toBe("Of 6,731 stored copies, 2,721 distinct messages remain after removing duplicates.");
    expect(funnelHeadline([])).toBeNull();
    expect(headerHeadline(data.tables.header_fields)).toBe(
      "Of 17 header fields, only Date is kept as metadata; Subject and X-Folder are content and never stored.",
    );
  });
});
