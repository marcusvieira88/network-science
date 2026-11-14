import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/AppShell";
import type { RunInfo } from "@/lib/data";
import { VIEWS } from "@/lib/views";

const run: RunInfo = {
  code_version: "abc1234",
  sample: true,
  seed: 20011202,
  parameters: { k_min: 5, window: "week", sensitivity_variants: ["cap=20", "window=month"] },
};

function renderShell(onSelect = vi.fn(), source: "release" | "sample" = "sample") {
  render(
    <AppShell active="overview" onSelect={onSelect} run={run} contractVersion="1.1" source={source}>
      <p>content</p>
    </AppShell>,
  );
  return onSelect;
}

describe("AppShell", () => {
  it("lists the eight views in order and marks the current one", () => {
    renderShell();
    const nav = screen.getByRole("navigation", { name: "Views" });
    const buttons = within(nav).getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual(VIEWS.map((v) => v.label));
    expect(within(nav).getByRole("button", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Overview");
  });

  it("selects a view by keyboard", async () => {
    const onSelect = renderShell();
    const user = userEvent.setup();
    // Skip link, Executive summary, Overview, then Metrics.
    await user.tab();
    await user.tab();
    await user.tab();
    await user.tab();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith("metrics");
  });

  it("offers a skip link to the content first", async () => {
    renderShell();
    const user = userEvent.setup();
    await user.tab();
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveFocus();
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
  });

  it("opens with the executive summary and ends with the glossary", () => {
    renderShell();
    const labels = within(screen.getByRole("navigation", { name: "Views" }))
      .getAllByRole("button")
      .map((b) => b.textContent);
    expect(labels[0]).toBe("Executive summary");
    expect(labels[labels.length - 1]).toBe("Glossary");
  });

  it("shows run details in the footer", () => {
    renderShell();
    const footer = screen.getByRole("contentinfo");
    expect(footer).toHaveTextContent("20011202");
    expect(footer).toHaveTextContent("abc1234");
    expect(footer).toHaveTextContent("k_min");
    expect(footer).toHaveTextContent("cap=20, window=month");
  });

  it("badges sample data visibly", () => {
    renderShell(vi.fn(), "sample");
    expect(screen.getByText("Sample data")).toBeInTheDocument();
  });

  it("badges release data", () => {
    renderShell(vi.fn(), "release");
    expect(screen.queryByText("Sample data")).not.toBeInTheDocument();
    expect(screen.getByText("Release data")).toBeInTheDocument();
  });
});
