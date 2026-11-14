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
    render(<FindingCard hypotheses={[h1]} />);
    expect(screen.getByText(/In-degree concentration \(Gini\) changed in the core network from the week of 2001-08-13/)).toBeInTheDocument();
    expect(screen.getByText("1.8")).toBeInTheDocument();
    expect(screen.getByText("[1.2, 2.4]")).toBeInTheDocument();
    expect(screen.getByText("0.008")).toBeInTheDocument();
    expect(screen.getByText("3 / 3")).toBeInTheDocument();
    expect(screen.getByText("high confidence")).toBeInTheDocument();
  });

  it("shows the no-finding state when no headline hypothesis is supported", () => {
    render(<FindingCard hypotheses={[{ ...h1, supported: "inconclusive" }]} />);
    expect(screen.getByText("No hypothesis supported")).toBeInTheDocument();
  });
});
