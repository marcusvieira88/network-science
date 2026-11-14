import { describe, expect, it } from "vitest";

import { type DeparturePeriodRow, type DepartureTestRow, type ReleaseData, parseRelease } from "@/lib/data";
import { PrivacyError, departureDisclosures, smallPersonCounts } from "@/lib/privacy";
import { realPeriods, realTests, withRealDepartures } from "@/test/departures";
import { rawSample, sampleData } from "@/test/sample";

function withPeriods(update: (rows: DeparturePeriodRow[]) => DeparturePeriodRow[]): ReleaseData {
  const data = withRealDepartures(sampleData());
  return { ...data, tables: { ...data.tables, departures: update(realPeriods()) } };
}

function withTests(update: (rows: DepartureTestRow[]) => DepartureTestRow[]): ReleaseData {
  const data = withRealDepartures(sampleData());
  return { ...data, tables: { ...data.tables, departure_tests: update(realTests()) } };
}

function setPeriod(name: DeparturePeriodRow["period"], values: Partial<DeparturePeriodRow>) {
  return (rows: DeparturePeriodRow[]) => rows.map((row) => (row.period === name ? { ...row, ...values } : row));
}

describe("H26 counts in the loaded data", () => {
  it("passes the sample and the real release's shape", () => {
    expect(departureDisclosures(sampleData())).toBe(0);
    expect(departureDisclosures(withRealDepartures(sampleData()))).toBe(0);
    expect(smallPersonCounts(withRealDepartures(sampleData()))).toBe(0);
  });

  it("counts an at-risk, departure or record-end count below k", () => {
    const data = withPeriods(setPeriod("crisis", { at_risk: 4, departures: 4, record_ends: 3 }));
    expect(smallPersonCounts(data)).toBe(3);
  });

  it("refuses a count whose complement in its row is below k", () => {
    // 66 at risk, 62 departed: the 4 who stayed would be revealed.
    expect(departureDisclosures(withPeriods(setPeriod("crisis", { departures: 62 })))).toBe(1);
    expect(departureDisclosures(withPeriods(setPeriod("crisis", { record_ends: 63 })))).toBe(1);
    // 30 departed and 33 ended of 66: 3 neither departed nor ended.
    expect(departureDisclosures(withPeriods(setPeriod("crisis", { departures: 30, record_ends: 33 })))).toBe(1);
    expect(departureDisclosures(withPeriods(setPeriod("crisis", { departures: 61, record_ends: null })))).toBe(0);
  });

  it("refuses a share published for a suppressed count", () => {
    expect(departureDisclosures(withPeriods(setPeriod("crisis", { hazard: 0.05 })))).toBe(1);
  });

  it("refuses a crisis split where two published counts reveal the third", () => {
    const twoOfThree = withPeriods((rows) =>
      setPeriod("crisis before the split", { departures: 8 })(setPeriod("crisis", { departures: 11 })(rows)),
    );
    expect(departureDisclosures(twoOfThree)).toBe(1);
    const endsTwoOfThree = withPeriods((rows) =>
      setPeriod("crisis from the split", { record_ends: 6 })(setPeriod("crisis", { record_ends: 9 })(rows)),
    );
    expect(departureDisclosures(endsTwoOfThree)).toBe(1);
    const allThree = withPeriods((rows) =>
      setPeriod("crisis from the split", { departures: 5 })(
        setPeriod("crisis before the split", { departures: 7 })(setPeriod("crisis", { departures: 12 })(rows)),
      ),
    );
    expect(departureDisclosures(allThree)).toBe(0);
  });

  it("refuses a p-value or a power count published for a robustness variant", () => {
    const variantP = withTests((rows) => rows.map((row) => (row.variant === "live 1" ? { ...row, p: 0.3 } : row)));
    expect(departureDisclosures(variantP)).toBe(1);
    const variantPower = withTests((rows) =>
      rows.map((row) => (row.variant === "live 1" ? { ...row, detectable_departures: 9 } : row)),
    );
    expect(departureDisclosures(variantPower)).toBe(1);
  });

  it("refuses to load a file with such a cell", () => {
    const raw = rawSample();
    const tables = raw.tables as Record<string, Record<string, unknown>[]>;
    tables.departures = (tables.departures ?? []).map((row) => (row.period === "reference" ? { ...row, hazard: 0.05 } : row));
    expect(() => parseRelease(raw)).toThrow(PrivacyError);
  });
});
