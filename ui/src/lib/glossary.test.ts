import { describe, expect, it } from "vitest";

import { GLOSSARY, glossaryMeaning } from "@/lib/glossary";

describe("glossary", () => {
  it("explains every term a leader meets in the explorer", () => {
    const terms = GLOSSARY.map((entry) => entry.term);
    for (const term of [
      "p (Holm)",
      "95% interval",
      "Placebo",
      "Leave-one-out",
      "Minimum group size (k)",
      "Re-identification",
      "Attackers A1, A2, A3",
      "Releases R0, R1, R2",
      "Pseudonym",
      "Confidence",
      "Retention check",
      "Robustness variants",
      "Core and observed network",
      "Precision and recall",
      "Anonymity set and unique share",
    ]) {
      expect(terms).toContain(term);
    }
  });

  it("lists each term once", () => {
    const terms = GLOSSARY.map((entry) => entry.term);
    expect(new Set(terms).size).toBe(terms.length);
  });

  it("looks a term up and refuses an unknown one", () => {
    expect(glossaryMeaning("Placebo")).toMatch(/^The same test run on a calm period/);
    expect(() => glossaryMeaning("Synergy")).toThrow('No glossary entry for "Synergy"');
  });
});
