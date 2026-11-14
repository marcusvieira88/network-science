import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { MetricChart } from "@/components/MetricChart";
import type { HypothesisRow, WeeklyMetricRow } from "@/lib/data";
import { analysisWeeks, metricSeries, snapToWeek, variants } from "@/lib/series";
import { sampleData } from "@/test/sample";

function row(week: string, value: number | null, variant = "default"): WeeklyMetricRow {
  return { scope: "core", week, metric: "density", value, n_active: value === null ? null : 12, variant };
}

describe("metric series", () => {
  const rows = [
    row("2000-01-17", 0.3),
    row("2000-01-03", 0.1),
    row("2000-01-10", null),
    row("2000-01-03", 0.9, "cap=20"),
  ];

  it("selects one metric, scope and variant in week order, keeping suppressed weeks as null", () => {
    expect(metricSeries(rows, { metric: "density", scope: "core", variant: "default" })).toEqual([
      { week: "2000-01-03", value: 0.1 },
      { week: "2000-01-10", value: null },
      { week: "2000-01-17", value: 0.3 },
    ]);
    expect(metricSeries(rows, { metric: "density", scope: "observed", variant: "default" })).toEqual([]);
  });

  it("lists the default variant first", () => {
    expect(variants(rows)).toEqual(["default", "cap=20"]);
  });

  it("snaps a date onto the week that contains it", () => {
    const weeks = analysisWeeks(rows);
    expect(snapToWeek(weeks, "2000-01-12")).toBe("2000-01-10");
    expect(snapToWeek(weeks, "2000-01-03")).toBe("2000-01-03");
    expect(snapToWeek(weeks, "1999-12-31")).toBeNull();
  });
});

describe("MetricChart", () => {
  const data = sampleData();
  const hypotheses: HypothesisRow[] = data.tables.hypotheses;

  it("marks the estimated change point, the baseline and every public event", () => {
    render(
      <MetricChart
        rows={data.tables.weekly_metrics}
        hypotheses={hypotheses}
        events={data.events}
        baseline={{ start: "2000-01-01", end: "2000-12-31" }}
        initialMetric="indegree_gini"
        initialScope="core"
      />,
    );
    const markers = screen.getByRole("list", { name: "Chart markers" });
    expect(markers).toHaveTextContent("Estimated change point: week of 2001-08-13 (H1)");
    expect(markers).toHaveTextContent("Baseline 2000-01-01 to 2000-12-31");
    for (const event of data.events) expect(markers).toHaveTextContent(event.label);
  });

  it("offers metric, scope and variant selectors", () => {
    render(
      <MetricChart rows={data.tables.weekly_metrics} hypotheses={hypotheses} events={[]} baseline={null} />,
    );
    expect(screen.getByRole("combobox", { name: "Metric" })).toHaveTextContent("Message volume");
    expect(screen.getByRole("combobox", { name: "Sensitivity variant" })).toHaveTextContent("default");
    expect(screen.getByRole("tab", { name: "core" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "observed" })).toBeInTheDocument();
  });

  it("says when a metric is not a tested hypothesis", () => {
    render(
      <MetricChart
        rows={data.tables.weekly_metrics}
        hypotheses={hypotheses}
        events={[]}
        baseline={null}
        initialMetric="volume"
      />,
    );
    expect(screen.getByRole("list", { name: "Chart markers" })).toHaveTextContent("not a pre-registered hypothesis");
  });

  it("switches the scope between core and observed from its tabs", async () => {
    const user = userEvent.setup();
    render(<MetricChart rows={data.tables.weekly_metrics} hypotheses={hypotheses} events={[]} baseline={null} />);
    await user.click(screen.getByRole("tab", { name: "observed" }));
    expect(screen.getByRole("tab", { name: "observed" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(/Weekly value, observed network/)).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "core" }));
    expect(screen.getByRole("tab", { name: "core" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(/Weekly value, core \(custodians\)/)).toBeInTheDocument();
  });
});
