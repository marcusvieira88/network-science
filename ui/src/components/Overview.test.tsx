import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Overview } from "@/components/Overview";
import { handBuilt } from "@/test/hypotheses";
import { sampleData } from "@/test/sample";

function dataWith(rows = handBuilt()) {
  const data = sampleData();
  return {
    ...data,
    tables: { ...data.tables, hypotheses: rows.hypotheses, exploratory: rows.exploratory, artifact_checks: rows.checks },
  };
}

describe("Overview", () => {
  it("adds a Held true line under the finding card for each held-true measure", () => {
    render(<Overview data={dataWith()} />);
    expect(
      screen.getByText("Held true: H16 — measure 16, change 0.25 (0.12 to 0.38), volume-equalised 0.1 (0.06 to 0.17)"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Exploratory:/)).not.toBeInTheDocument();
  });

  it("adds no line when nothing is held true", () => {
    const rows = handBuilt();
    const exploratory = rows.exploratory.map((row) => ({ ...row, outcome: "inconclusive" as const }));
    render(<Overview data={dataWith({ ...rows, exploratory })} />);
    expect(screen.queryByText(/^Held true:/)).not.toBeInTheDocument();
  });

  it("answers first, in plain words, with the reasons and the privacy result", () => {
    render(<Overview data={dataWith()} />);
    // handBuilt: H1 is the headline and H16 is confident; the other 22 show no reliable change.
    expect(screen.getByText("2 of 24 hypotheses held up: H1, H16.")).toBeInTheDocument();
    expect(screen.getByText("22 showed no reliable change.")).toBeInTheDocument();
    expect(screen.getByText(/cuts the strongest attacker's re-identification rate from/)).toBeInTheDocument();
  });

  it("counts only real groups in the key numbers and names the outside bucket's size apart", () => {
    const data = dataWith();
    const groups = [
      { group: "G01", n_persons: 926 },
      { group: "G02", n_persons: 743 },
      { group: "other", n_persons: 25838 },
    ];
    render(<Overview data={{ ...data, tables: { ...data.tables, community_groups: groups } }} />);
    const header = screen.getByText("Groups in the network view").parentElement;
    expect(header).toHaveTextContent("Groups in the network view2");
    expect(header?.nextElementSibling).toHaveTextContent("each at least 5 people; 25,838 more people are outside the 2000 groups");
  });

  it("leads to the plain-language hypotheses and to the network", async () => {
    const onSelect = vi.fn();
    render(<Overview data={dataWith()} onSelect={onSelect} />);
    await userEvent.click(screen.getByRole("button", { name: /Every hypothesis in plain words/ }));
    await userEvent.click(screen.getByRole("button", { name: /See how the groups talk/ }));
    expect(onSelect.mock.calls).toEqual([["hypotheses"], ["network"]]);
  });
});
