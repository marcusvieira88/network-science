import { describe, expect, it } from "vitest";

import type { ArtifactCheckRow, HypothesisRow } from "@/lib/data";
import { noFindingExplanation } from "@/lib/finding";

function hypothesis(id: HypothesisRow["hypothesis"], over: Partial<HypothesisRow>): HypothesisRow {
  return {
    hypothesis: id,
    metric: "external_share",
    scope: "observed",
    change_week: null,
    p_perm: 0.5,
    p_holm: 0.9,
    effect: 0.1,
    ci_low: -0.2,
    ci_high: 0.4,
    null_z: 0,
    loo_min_effect: -0.1,
    loo_max_effect: 0.3,
    robust_variants_passed: 0,
    robust_variants_total: 2,
    supported: "no",
    confidence: "low",
    is_headline: false,
    ...over,
  };
}

function check(id: ArtifactCheckRow["hypothesis"], passes: boolean | null): ArtifactCheckRow {
  return {
    hypothesis: id,
    check: "within_custodian",
    statistic: passes === null ? null : 0.1,
    ci_low: passes === null ? null : 0.0,
    ci_high: passes === null ? null : 0.2,
    n_units: null,
    passes,
    note: "",
  };
}

describe("noFindingExplanation", () => {
  it("says no hypothesis is supported when none is", () => {
    const text = noFindingExplanation([hypothesis("H1", {}), hypothesis("H2", { supported: "inconclusive" })], []);
    expect(text.title).toBe("No hypothesis supported");
    expect(text.body.join(" ")).not.toMatch(/passed/);
  });

  it("names supported hypotheses that failed or could not run an artifact check", () => {
    const hypotheses = [
      hypothesis("H1", {}),
      hypothesis("H2", { supported: "yes" }),
      hypothesis("H3", { supported: "yes" }),
    ];
    const text = noFindingExplanation(hypotheses, [check("H2", false), check("H3", null)]);
    expect(text.title).toBe("No behavioural finding claimed");
    const body = text.body.join(" ");
    expect(body).toMatch(/H2 passed the statistical tests but failed its check against a known artifact/);
    expect(body).toMatch(/H3 passed the statistical tests but its check against a known artifact could not run/);
    expect(body).toMatch(/so no behavioural finding is claimed/);
    expect(body).not.toMatch(/H1/);
  });

  it("explains a supported hypothesis that is not headline because a robustness check failed", () => {
    const text = noFindingExplanation([hypothesis("H4", { supported: "yes", confidence: "moderate" })], []);
    expect(text.title).toBe("No behavioural finding claimed");
    expect(text.body.join(" ")).toMatch(/H4 is supported but fails at least one robustness check \(moderate confidence\)/);
  });
});
