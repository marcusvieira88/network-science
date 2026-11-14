import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FindingCard } from "@/components/FindingCard";
import type { HypothesisRow } from "@/lib/data";

const h1: HypothesisRow = {
  hypothesis: "H1",
  metric: "indegree_gini",
  scope: "core",
  change_week: "2001-08-13",
  p_perm: 0.002,
  p_holm: 0.008,
  effect: 1.8,
  ci_low: 1.2,
  ci_high: 2.4,
  null_z: 4.1,
  loo_min_effect: 1.5,
  loo_max_effect: 2,
  robust_variants_passed: 3,
  robust_variants_total: 3,
  supported: "yes",
  confidence: "high",
  is_headline: true,
};

describe("FindingCard", () => {
  it("shows the headline claim, effect, interval and confidence", () => {
    render(<FindingCard hypotheses={[h1]} artifactChecks={[]} />);
    expect(screen.getByText(/In-degree concentration \(Gini\) changed in the core network from the week of 2001-08-13/)).toBeInTheDocument();
    expect(screen.getByText("1.8")).toBeInTheDocument();
    expect(screen.getByText("[1.2, 2.4]")).toBeInTheDocument();
    expect(screen.getByText("0.008")).toBeInTheDocument();
    expect(screen.getByText("3 / 3")).toBeInTheDocument();
    expect(screen.getByText("high confidence")).toBeInTheDocument();
  });

  it("states the finding about the record before what is not claimed about behaviour", () => {
    const finding =
      "The finding: the record changed (high confidence that it changed; cause not established). No behavioural finding about the crisis year is claimed.";
    render(
      <FindingCard hypotheses={[{ ...h1, supported: "no", is_headline: false }]} artifactChecks={[]} recordFinding={finding} />,
    );
    expect(screen.getByText(finding)).toBeInTheDocument();
    expect(screen.getByText("Headline among the pre-registered hypotheses")).toBeInTheDocument();
    expect(screen.queryByText(/no finding/i)).not.toBeInTheDocument();
  });

  it("keeps the finding about the record next to a behavioural headline", () => {
    const finding = "The finding: the record changed (high confidence that it changed; cause not established).";
    render(<FindingCard hypotheses={[h1]} artifactChecks={[]} recordFinding={finding} />);
    expect(screen.getByText(finding)).toBeInTheDocument();
    expect(screen.getByText("high confidence")).toBeInTheDocument();
  });

  it("shows the no-finding state when no headline hypothesis is supported", () => {
    render(<FindingCard hypotheses={[{ ...h1, supported: "inconclusive", is_headline: false }]} artifactChecks={[]} />);
    expect(screen.getByText("No hypothesis supported")).toBeInTheDocument();
    expect(screen.queryByText(/passed the test/)).not.toBeInTheDocument();
  });

  it("says a supported hypothesis failed its artifact check instead of 'none passed'", () => {
    const failed = {
      hypothesis: "H1" as const,
      check: "baseline_placebo",
      statistic: 3.1,
      ci_low: 2.2,
      ci_high: 4,
      n_units: 26,
      passes: false,
      note: "",
    };
    render(<FindingCard hypotheses={[{ ...h1, confidence: "low", is_headline: false }]} artifactChecks={[failed]} />);
    expect(screen.getByText("No behavioural finding claimed")).toBeInTheDocument();
    expect(screen.getByText(/H1 passed the statistical tests but failed its check against a known artifact/)).toBeInTheDocument();
  });
});
