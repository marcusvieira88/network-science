import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LIMITS, Limits } from "@/components/Limits";

describe("Limits", () => {
  it("names every limit", () => {
    render(<Limits sample={false} />);
    for (const limit of LIMITS) expect(screen.getByText(limit.title)).toBeInTheDocument();
    expect(screen.queryByText(/synthetic sample corpus/)).not.toBeInTheDocument();
  });

  it("warns when the numbers come from the synthetic sample", () => {
    render(<Limits sample />);
    expect(screen.getByText(/synthetic sample corpus/)).toBeInTheDocument();
  });
});
