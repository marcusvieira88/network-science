import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Explain } from "@/components/Explain";
import { glossaryMeaning } from "@/lib/glossary";

describe("Explain", () => {
  it("shows the plain meaning on demand, by keyboard", async () => {
    render(<Explain term="Placebo" />);
    const button = screen.getByRole("button", { name: "What does “Placebo” mean?" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    const note = screen.getByText(glossaryMeaning("Placebo"));
    expect(note).not.toBeVisible();
    // No display utility while closed: in a browser it would override the hidden attribute.
    expect(note).toHaveClass("hidden");
    expect(note).not.toHaveClass("block");
    button.focus();
    await userEvent.keyboard("{Enter}");
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(glossaryMeaning("Placebo"))).toBeVisible();
  });

  it("adds no text to the label it sits in", () => {
    render(
      <dt>
        95% interval <Explain term="95% interval" />
      </dt>,
    );
    expect(screen.getByText("95% interval").textContent?.startsWith("95% interval")).toBe(true);
    expect(screen.getByRole("button").textContent).toBe("");
  });
});
