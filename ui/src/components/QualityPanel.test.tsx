import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QualityPanel } from "@/components/QualityPanel";
import { sampleData } from "@/test/sample";

describe("QualityPanel", () => {
  const { tables } = sampleData();

  function renderPanel() {
    render(
      <QualityPanel steps={tables.data_quality} headerFields={tables.header_fields} degrees={tables.degree_distribution} />,
    );
  }

  it("shows the cleaning funnel with counts and precision and recall", () => {
    renderPanel();
    expect(screen.getByText("2. deduplicate")).toBeInTheDocument();
    expect(screen.getByText(/6,731 → 2,721/)).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "deduplicate: share kept" })).toHaveAttribute(
      "aria-valuenow",
      String(2721 / 6731),
    );
    expect(screen.getAllByText(/Precision 100% · recall 100%/)).toHaveLength(2);
  });

  it("shows the header ruling for every field", () => {
    renderPanel();
    expect(screen.getByText("Subject")).toBeInTheDocument();
    expect(screen.getAllByText("content").length).toBeGreaterThan(0);
  });

  it("orders degree buckets numerically and shows suppressed cells", () => {
    renderPanel();
    const labels = screen.getAllByRole("row").map((row) => row.firstChild?.textContent);
    expect(labels.filter((l) => ["1", "2-4", "5-9", "10+"].includes(l ?? ""))).toEqual(["1", "2-4", "5-9", "10+"]);
    // Per half-year: the 10+ cell below k and its complementary suppression in bucket 1.
    expect(screen.getAllByText("suppressed")).toHaveLength(8);
  });
});
