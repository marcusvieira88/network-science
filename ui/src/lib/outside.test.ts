import { describe, expect, it } from "vitest";

import type { CommunityEdgeRow, CommunityGroupRow } from "@/lib/data";
import {
  OUTSIDE_SHORT,
  displayGroup,
  outsideExplanation,
  outsideLabel,
  outsidePeople,
  outsideTies,
  outsideWeekCaption,
  outsideWeekShare,
} from "@/lib/outside";

const BASELINE_2000 = { start: "2000-01-01", end: "2000-12-31" };

function row(week: string, src: string, dst: string, nMessages: number | null, weight = 1): CommunityEdgeRow {
  return { week, src_group: src, dst_group: dst, weight, n_messages: nMessages };
}

describe("outsideLabel", () => {
  it("names the baseline year when the baseline is one calendar year", () => {
    expect(outsideLabel(BASELINE_2000)).toBe("Outside the 2000 groups");
  });

  it("falls back to 'baseline' when the baseline spans years or is unknown", () => {
    expect(outsideLabel({ start: "2000-07-01", end: "2001-06-30" })).toBe("Outside the baseline groups");
    expect(outsideLabel(null)).toBe("Outside the baseline groups");
  });

  it("has a short form for tight spaces", () => {
    expect(OUTSIDE_SHORT).toBe("outside");
  });
});

describe("displayGroup", () => {
  it("shows the outside label for the release's other bucket and real labels unchanged", () => {
    expect(displayGroup("other", BASELINE_2000)).toBe("Outside the 2000 groups");
    expect(displayGroup("G01", BASELINE_2000)).toBe("G01");
  });
});

describe("outsidePeople and outsideExplanation", () => {
  const groups: CommunityGroupRow[] = [
    { group: "G01", n_persons: 926 },
    { group: "other", n_persons: 25838 },
  ];

  it("reads the bucket's size from community_groups, or null when it is not published", () => {
    expect(outsidePeople(groups)).toBe(25838);
    expect(outsidePeople([{ group: "G01", n_persons: 926 }])).toBeNull();
  });

  it("says in one sentence who is in the bucket and that it is not a community", () => {
    expect(outsideExplanation(25838, 5, BASELINE_2000)).toBe(
      "25,838 people with no tie in 2000 (mostly people who first appear later) or in groups under 5 people; not a community.",
    );
    expect(outsideExplanation(7, 5, null)).toBe(
      "7 people with no tie in the baseline period (mostly people who first appear later) or in groups under 5 people; not a community.",
    );
  });
});

describe("outsideWeekShare", () => {
  it("is the week's message counts touching the bucket over all the week's published counts", () => {
    // Hand-computed: 30 + 10 + 60 + 40 (named) + 500 + 25 + 335 (touching other) = 1000; 860 / 1000.
    const edges = [
      row("2001-10-22", "G01", "G02", 30),
      row("2001-10-22", "G02", "G01", 10),
      row("2001-10-22", "G01", "G01", 60),
      row("2001-10-22", "G02", "G02", 40),
      row("2001-10-22", "G02", "other", 500),
      row("2001-10-22", "other", "G01", 25),
      row("2001-10-22", "other", "other", 335),
      row("2001-10-29", "G01", "other", 999),
    ];
    expect(outsideWeekShare(edges, "2001-10-22")).toBeCloseTo(0.86, 12);
  });

  it("counts a suppressed row as 0 and is null for a week with nothing published", () => {
    const edges = [row("2001-10-22", "G01", "G02", 3), row("2001-10-22", "G01", "other", null)];
    expect(outsideWeekShare(edges, "2001-10-22")).toBe(0);
    expect(outsideWeekShare(edges, "2001-11-05")).toBeNull();
    expect(outsideWeekShare(edges, null)).toBeNull();
  });
});

describe("outsideWeekCaption", () => {
  it("states the share as mail counted per sender–recipient pair", () => {
    expect(outsideWeekCaption(0.6462800799834517, BASELINE_2000)).toBe(
      "64.6% of this week's mail (counted per sender–recipient pair) involves people outside the 2000 groups.",
    );
  });

  it("says when nothing was published that week", () => {
    expect(outsideWeekCaption(null, BASELINE_2000)).toBe("No mail between people was published for this week.");
  });
});

describe("outsideTies", () => {
  it("sums the week's weight between the bucket and the real groups into one summary", () => {
    const edges = [
      row("2001-10-22", "G01", "other", 0, 4),
      row("2001-10-22", "other", "G02", 0, 1.5),
      row("2001-10-22", "other", "other", 0, 100),
      row("2001-10-22", "G01", "G02", 0, 9),
      row("2001-10-29", "G01", "other", 0, 50),
    ];
    expect(outsideTies(edges, "2001-10-22")).toEqual({ weight: 5.5, groups: 2 });
    expect(outsideTies(edges, "2001-11-05")).toEqual({ weight: 0, groups: 0 });
  });
});
