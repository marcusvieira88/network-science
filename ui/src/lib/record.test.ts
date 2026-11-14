import { describe, expect, it } from "vitest";

import type { ExploratoryRow, RecordProfileRow, ReleaseData } from "@/lib/data";
import { NO_BEHAVIOURAL_FINDING, recordConfidence, recordFinding, windowShares } from "@/lib/record";
import { exploratory } from "@/test/hypotheses";
import { sampleData } from "@/test/sample";

/** One profile row per month, August 2000 to December 2001, with the given after-hours shares. */
function profile(shares: (number | null)[]): RecordProfileRow[] {
  const months = [8, 9, 10, 11, 12].map((m) => `2000-${String(m).padStart(2, "0")}-01`);
  for (let m = 1; m <= 12; m += 1) months.push(`2001-${String(m).padStart(2, "0")}-01`);
  return months.map((month, index) => ({
    month,
    custodians_sending: 10,
    sent_messages: 100,
    after_hours_share: shares[index] ?? null,
    custodians_receiving: 12,
    received_messages: 300,
  }));
}

/** Reference months (Aug–Nov 2000) 0.45–0.55; crisis months (Aug–Nov 2001) 0.06–0.1: the ranges do not overlap. */
const SWITCHED = [0.5, 0.45, 0.55, 0.48, 0.5, 0.5, 0.47, 0.5, 0.56, 0.6, 0.25, 0.14, 0.1, 0.07, 0.06, 0.06, 0.09];
const FLAT = SWITCHED.map(() => 0.5);

/** H5 with the interval median ± 0.05. */
function h5(median: number | null): ExploratoryRow {
  return exploratory(5, {
    median_change: median,
    ci_low: median === null ? null : median - 0.05,
    ci_high: median === null ? null : median + 0.05,
  });
}

function dataWith(shares: (number | null)[], rows: ExploratoryRow[]): ReleaseData {
  const data = sampleData();
  return {
    ...data,
    windows: { reference: { start: "2000-08-14", end: "2000-12-02" }, crisis: { start: "2001-08-14", end: "2001-12-02" } },
    tables: { ...data.tables, record_profile: profile(shares), exploratory: rows },
  };
}

describe("windowShares", () => {
  it("takes the months from the window's first month up to, not including, the month of its end", () => {
    expect(windowShares(profile(SWITCHED), { start: "2000-08-14", end: "2000-12-02" })).toEqual([0.5, 0.45, 0.55, 0.48]);
    expect(windowShares(profile(SWITCHED), { start: "2001-08-14", end: "2001-12-02" })).toEqual([0.1, 0.07, 0.06, 0.06]);
  });

  it("skips suppressed months", () => {
    const shares = [null, ...SWITCHED.slice(1)];
    expect(windowShares(profile(shares), { start: "2000-08-14", end: "2000-12-02" })).toEqual([0.45, 0.55, 0.48]);
  });
});

describe("recordConfidence (the rule of report/record.py)", () => {
  it("is high when the ranges do not overlap and the H5 interval excludes zero", () => {
    expect(recordConfidence(dataWith(SWITCHED, [h5(-0.44)]))).toBe("high");
  });

  it("is moderate when the ranges do not overlap but H5 holds zero, is suppressed or is absent", () => {
    expect(recordConfidence(dataWith(SWITCHED, [h5(-0.02)]))).toBe("moderate");
    expect(recordConfidence(dataWith(SWITCHED, [h5(null)]))).toBe("moderate");
    expect(recordConfidence(dataWith(SWITCHED, []))).toBe("moderate");
  });

  it("claims no change when the ranges overlap or a window has no published month", () => {
    expect(recordConfidence(dataWith(FLAT, [h5(-0.44)]))).toBeNull();
    const hidden = SWITCHED.map((share, index) => (index < 4 ? null : share));
    expect(recordConfidence(dataWith(hidden, [h5(-0.44)]))).toBeNull();
  });

  it("reads a rise of the share as a change too", () => {
    expect(recordConfidence(dataWith(SWITCHED.map((share) => 1 - share), [h5(0.44)]))).toBe("high");
  });
});

describe("recordFinding", () => {
  it("is the one sentence every surface uses, with the derived confidence", () => {
    expect(recordFinding(dataWith(SWITCHED, [h5(-0.44)]))).toBe(
      "The finding: the record changed (high confidence that it changed; cause not established).",
    );
    expect(recordFinding(dataWith(SWITCHED, []))).toBe(
      "The finding: the record changed (moderate confidence that it changed; cause not established).",
    );
    expect(recordFinding(dataWith(FLAT, [h5(-0.44)]))).toBeNull();
    expect(NO_BEHAVIOURAL_FINDING).toBe("No behavioural finding about the crisis year is claimed.");
  });
});
