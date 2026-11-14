import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { App } from "@/App";
import { LIMITS } from "@/components/Limits";
import { SummaryView } from "@/components/SummaryView";
import { summaryCards, whatItMeans } from "@/lib/executive";
import { sampleData } from "@/test/sample";

describe("SummaryView", () => {
  const data = sampleData();

  it("shows six cards in plain words, each with its points", () => {
    render(<SummaryView data={data} onSelect={vi.fn()} />);
    const cards = screen.getAllByRole("article");
    expect(cards).toHaveLength(6);
    for (const [index, card] of summaryCards(data).entries()) {
      const article = cards[index];
      if (!article) throw new Error(`card ${card.key} missing`);
      expect(within(article).getByRole("heading", { level: 2 })).toHaveTextContent(card.title);
      for (const point of card.points) expect(within(article).getByText(point)).toBeInTheDocument();
    }
    expect(screen.getByRole("heading", { level: 2, name: "2 of 26 hypotheses held up: H1, H26." })).toBeInTheDocument();
  });

  it("leads from each card to its evidence view", async () => {
    const onSelect = vi.fn();
    render(<SummaryView data={data} onSelect={onSelect} />);
    for (const card of summaryCards(data)) {
      const buttons = screen.getAllByRole("button", { name: new RegExp(card.linkLabel) });
      for (const button of buttons) await userEvent.click(button);
    }
    expect(onSelect.mock.calls.map((call) => call[0])).toEqual(["quality", "hypotheses", "hypotheses", "limits", "risk", "quality"]);
  });

  it("says what it means for an organisation and what it cannot tell", () => {
    render(<SummaryView data={data} onSelect={vi.fn()} />);
    const means = screen.getByRole("region", { name: "What this means for a real organisation" });
    for (const line of whatItMeans(data)) expect(within(means).getByText(line)).toBeInTheDocument();
    const cannot = screen.getByRole("region", { name: "What this cannot tell you" });
    for (const limit of LIMITS) expect(within(cannot).getByText(limit.plain)).toBeInTheDocument();
  });

  it("warns that the sample is synthetic", () => {
    render(<SummaryView data={data} onSelect={vi.fn()} />);
    expect(screen.getByText(/synthetic sample corpus, not from the Enron data/)).toBeInTheDocument();
  });

  it("prints the summary", async () => {
    const print = vi.spyOn(window, "print").mockImplementation(() => undefined);
    render(<SummaryView data={data} onSelect={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /Print this summary/ }));
    expect(print).toHaveBeenCalledOnce();
    print.mockRestore();
  });
});

describe("App", () => {
  it("opens on the executive summary and reaches the glossary from the navigation", async () => {
    render(<App load={() => Promise.resolve({ status: "ok", data: sampleData(), source: "sample" })} />);
    expect(await screen.findByRole("heading", { level: 1, name: "Executive summary" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Glossary" }));
    expect(screen.getByRole("heading", { level: 1, name: "Glossary" })).toBeInTheDocument();
    expect(screen.getByText("Pseudonym")).toBeInTheDocument();
  });

  it("opens an evidence link at the top of the new view, with focus on its content", async () => {
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
    render(<App load={() => Promise.resolve({ status: "ok", data: sampleData(), source: "sample" })} />);
    await userEvent.click(await screen.findByRole("button", { name: /See the attacks/ }));
    expect(screen.getByRole("heading", { level: 1, name: "Privacy and risk" })).toBeInTheDocument();
    expect(scrollTo).toHaveBeenCalledWith(0, 0);
    expect(document.activeElement).toBe(screen.getByRole("main"));
    scrollTo.mockRestore();
  });
});
