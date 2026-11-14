/**
 * A small hand-built set of hypotheses with the single numbering: H1–H4 in the `hypotheses` table,
 * H5–H24 in the `exploratory` table (H25 and H26 are added by the tests that need them). Tests use it instead of the sample's ids.
 */
import type { ArtifactCheckRow, ExploratoryRow, HypothesisRow } from "@/lib/data";

const FIRST_EXPLORATORY = 5;
const LAST_EXPLORATORY = 24;

export function preregistered(id: HypothesisRow["hypothesis"], overrides: Partial<HypothesisRow> = {}): HypothesisRow {
  return {
    hypothesis: id,
    metric: "indegree_gini",
    scope: "core",
    change_week: null,
    p_perm: 0.2,
    p_holm: 0.6,
    effect: 0.3,
    ci_low: -0.2,
    ci_high: 0.8,
    null_z: 0.5,
    loo_min_effect: 0.1,
    loo_max_effect: 0.4,
    robust_variants_passed: 0,
    robust_variants_total: 3,
    supported: "no",
    confidence: "low",
    is_headline: false,
    ...overrides,
  };
}

export function exploratory(number: number, overrides: Partial<ExploratoryRow> = {}): ExploratoryRow {
  return {
    order: number - FIRST_EXPLORATORY + 1,
    hypothesis: `H${number}`,
    family: number < 15 ? "first" : "second",
    measure: `measure ${number}`,
    direction: "up",
    custodians: 30,
    median_change: 0.01,
    ci_low: -0.02,
    ci_high: 0.04,
    p: 0.4,
    p_holm: 1,
    placebo_custodians: 20,
    placebo_median: 0,
    placebo_ci_low: -0.01,
    placebo_ci_high: 0.01,
    placebo_passes: true,
    loo_stable: false,
    outcome: "not supported",
    caveat: "",
    equalised_median: null,
    equalised_ci_low: null,
    equalised_ci_high: null,
    equalised_p: null,
    equalised_p_holm: null,
    retention_median: null,
    retention_ci_low: null,
    retention_ci_high: null,
    retention_passes: null,
    ...overrides,
  };
}

export function check(id: ArtifactCheckRow["hypothesis"], overrides: Partial<ArtifactCheckRow> = {}): ArtifactCheckRow {
  return {
    hypothesis: id,
    check: "baseline_placebo",
    statistic: 0.4,
    ci_low: -0.3,
    ci_high: 1.1,
    n_units: 26,
    passes: true,
    note: "out-of-sample jump within the calm baseline year is small",
    ...overrides,
  };
}

/** H1 is the headline; H16 is confident with a volume-equalised result; H6 has a caveat. */
export function handBuilt(): { hypotheses: HypothesisRow[]; exploratory: ExploratoryRow[]; checks: ArtifactCheckRow[] } {
  const numbers = Array.from({ length: LAST_EXPLORATORY - FIRST_EXPLORATORY + 1 }, (_, i) => FIRST_EXPLORATORY + i);
  return {
    hypotheses: [
      preregistered("H1", {
        is_headline: true,
        supported: "yes",
        confidence: "high",
        effect: 1.8,
        ci_low: 1.2,
        ci_high: 2.4,
        p_holm: 0.008,
        change_week: "2001-08-13",
      }),
      preregistered("H2", { metric: "cross_community_share", scope: "observed" }),
      preregistered("H3", { metric: "external_share", scope: "observed" }),
      preregistered("H4", { metric: "tie_turnover" }),
    ],
    exploratory: numbers.map((number) => {
      if (number === 16) {
        return exploratory(16, {
          median_change: 0.25,
          ci_low: 0.12,
          ci_high: 0.38,
          p_holm: 0.002,
          loo_stable: true,
          outcome: "confident",
          equalised_median: 0.1,
          equalised_ci_low: 0.06,
          equalised_ci_high: 0.17,
          equalised_p: 0.001,
        });
      }
      if (number === 6) return exploratory(6, { direction: "down", caveat: "timestamps are shifted in this window" });
      return exploratory(number);
    }),
    checks: [check("H2"), check("H3", { check: "external_domain_drift", passes: false, note: "drift explains it" })],
  };
}
