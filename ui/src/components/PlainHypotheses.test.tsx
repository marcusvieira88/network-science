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
    expect(items[0]).toHaveTextContent("H2Explained by the data");
    expect(items[0]).toHaveTextContent("a quirk of the data explains it: drift explains it.");
  });

  it("folds the hypotheses with no reliable change under one line", () => {
    render(<PlainHypotheses entries={entries} />);
    expect(screen.getByText("2 more with no reliable change or withheld — show them")).toBeInTheDocument();
  });
});

describe("Glossary", () => {
  it("defines every term in plain words", () => {
    render(<Glossary />);
    for (const { term } of GLOSSARY) expect(screen.getByText(term)).toBeInTheDocument();
  });
});
