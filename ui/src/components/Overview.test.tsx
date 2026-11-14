import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Overview } from "@/components/Overview";
import { withRealDepartures } from "@/test/departures";
import { handBuilt } from "@/test/hypotheses";
import { sampleData } from "@/test/sample";

function dataWith(rows = handBuilt()) {
  const data = withRealDepartures(sampleData());
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
    // The real H26 follows its 24 hypotheses, so it is numbered H25 here and has a sentence of its own.
    expect(screen.getByText("2 of 25 hypotheses held up: H1, H16.")).toBeInTheDocument();
    expect(screen.getByText("22 showed no reliable change.")).toBeInTheDocument();
    expect(screen.getByText(/^No structural change can be established: H25 asked whether custodians left/)).toBeInTheDocument();
    expect(screen.getByText(/re-identifies .* of people/)).toBeInTheDocument();
  });

  it("states both rates without the by-construction wording when the published rate is not 0", () => {
    const data = dataWith();
    const template = data.tables.risk[0];
    if (!template) throw new Error("sample has no risk row");
    const risk = [
      { ...template, release_variant: "R0" as const, attacker: "A2" as const, reid_top1: 0.5 },
      { ...template, release_variant: "R1" as const, attacker: "A2" as const, reid_top1: 0.04 },
    ];
    render(<Overview data={{ ...data, tables: { ...data.tables, risk } }} />);
    expect(
      screen.getByText(
        "On person-level pseudonymised data the strongest attack re-identifies 50% of people; on the published " +
          "release, 4%.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("strongest attacker, person-level data vs published")).toBeInTheDocument();
  });

  it("says the published 0% re-identification holds by construction, not as a measured attack", () => {
    const data = dataWith();
    const template = data.tables.risk[0];
    if (!template) throw new Error("sample has no risk row");
    const risk = [
      { ...template, release_variant: "R0" as const, attacker: "A1" as const, reid_top1: 0.2513 },
      { ...template, release_variant: "R0" as const, attacker: "A2" as const, reid_top1: 0.5910745371103022 },
      { ...template, release_variant: "R1" as const, attacker: "A2" as const, reid_top1: 0 },
    ];
    render(<Overview data={{ ...data, tables: { ...data.tables, risk } }} />);
    expect(
      screen.getByText(
        "On person-level pseudonymised data the strongest attack re-identifies 59.1% of people. The published " +
          "release holds only groups of at least 5 people, so that attack has no person to match there (0%, by " +
          "construction); no attack on the group tables was run.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("strongest attacker; the published tables hold no person to match")).toBeInTheDocument();
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
