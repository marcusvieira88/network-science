/**
 * H26 as the real release publishes it (values copied from release/departures.csv and
 * release/departure_tests.csv): every departure and record-end count is suppressed, the outcome
 * is "not established", and the power columns say 9 of 66 (placebo 16 of 51) were needed.
 */
import type { DeparturePeriodRow, DepartureTestRow, ReleaseData } from "@/lib/data";

function period(
  order: number,
  name: DeparturePeriodRow["period"],
  start: string,
  end: string,
  atRisk: number,
): DeparturePeriodRow {
  return { order, period: name, period_start: start, period_end: end, at_risk: atRisk, departures: null, record_ends: null, hazard: null };
}

export function realPeriods(): DeparturePeriodRow[] {
  return [
    period(1, "crisis", "2001-08-14", "2001-12-02", 66),
    period(2, "reference", "2000-08-14", "2000-12-02", 26),
    period(3, "placebo after", "2001-01-01", "2001-04-30", 51),
    period(4, "placebo before", "2000-01-01", "2000-04-30", 9),
    period(5, "crisis before the split", "2001-08-14", "2001-10-15", 66),
    period(6, "crisis from the split", "2001-10-16", "2001-12-02", 66),
  ];
}

function variant(
  order: number,
  name: string,
  above: boolean | null,
  rolling: number,
  aboveRolling: boolean | null,
  inRule = true,
): DepartureTestRow {
  const band = above === null ? null : ("alpha or above" as const);
  return {
    order,
    variant: name,
    in_rule: inRule,
    crisis_above_reference: above,
    p: null,
    p_band: band,
    placebo_p: null,
    placebo_p_band: band,
    rolling_windows: rolling,
    above_rolling: aboveRolling,
    loo_stable: null,
    outcome: null,
    detectable_departures: null,
    placebo_detectable_departures: null,
  };
}

export function realTests(): DepartureTestRow[] {
  return [
    { ...variant(1, "primary", false, 55, false), loo_stable: false, outcome: "not established", detectable_departures: 9, placebo_detectable_departures: 16 },
    variant(2, "silence 8", false, 53, false),
    variant(3, "silence 26", false, 55, false),
    variant(4, "live 1", true, 55, false),
    variant(5, "live 8", false, 55, false),
    variant(6, "active 2", false, 65, false),
    variant(7, "active 8", null, 37, null),
    variant(8, "custodian-visible", true, 37, true),
    variant(9, "same cohort", false, 55, false),
    variant(10, "no successor", false, 55, false),
    variant(11, "any silence", true, 55, false, false),
  ];
}

/** `data` with the real release's H26 tables. */
export function withRealDepartures(data: ReleaseData): ReleaseData {
  return { ...data, tables: { ...data.tables, departures: realPeriods(), departure_tests: realTests() } };
}
