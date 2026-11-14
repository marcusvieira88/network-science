import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Glossary } from "@/components/Glossary";
import { PlainHypotheses } from "@/components/PlainHypotheses";
import { GLOSSARY } from "@/lib/glossary";
import { allHypotheses } from "@/lib/hypotheses";
import { check, exploratory, preregistered } from "@/test/hypotheses";

describe("PlainHypotheses", () => {
  const entries = allHypotheses(
    [preregistered("H2", { supported: "yes" }), preregistered("H4")],
    [exploratory(5, { caveat: "invalid: timestamps are shifted" }), exploratory(9)],
    [check("H2", { passes: false, note: "drift explains it" })],
  );

  it("shows the noteworthy outcomes first, each with its verdict and one sentence", () => {
    render(<PlainHypotheses entries={entries} />);
    const list = screen.getAllByRole("list")[0];
    if (!list) throw new Error("no list");
    const items = within(list).getAllByRole("listitem");
    expect(items.map((item) => item.getAttribute("data-verdict"))).toEqual(["artifact", "untestable"]);
    expect(items[0]).toHaveTextContent("H2Explained by an artifact");
    expect(items[0]).toHaveTextContent("a known artifact of the data or the method explains it: drift explains it.");
  });

  it("folds the hypotheses with no reliable change under one line", () => {
    render(<PlainHypotheses entries={entries} />);
    expect(screen.getByText("2 more not established or withheld — show them")).toBeInTheDocument();
  });
});

describe("Glossary", () => {
  it("defines every term in plain words", () => {
    render(<Glossary />);
    for (const { term } of GLOSSARY) expect(screen.getByText(term)).toBeInTheDocument();
  });

  it("says what the release supports: groups of at least the minimum size, and people outside them as no group", () => {
    const meaning = (term: string) => GLOSSARY.find((entry) => entry.term === term)?.meaning ?? "";
    expect(meaning("Group")).toContain("at least a minimum size");
    expect(meaning("Group")).not.toContain("above a minimum size");
    expect(meaning("Outside the baseline groups")).toContain("not a group");
    // H2's artifact is the method (groups fixed on the baseline going stale), not only the data.
    expect(meaning("Artifact check")).toContain("the method");
    expect(meaning("Placebo")).not.toContain("picking up noise");
    // Stable means the predicted direction survives every omission; it is not a claim about one person.
    expect(meaning("Leave-one-out")).toContain("keeps the predicted direction every time");
    expect(meaning("Leave-one-out")).not.toContain("no single person drives");
    expect(meaning("Placebo")).toContain("no change in the predicted direction");
  });
});
