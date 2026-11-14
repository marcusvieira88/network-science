/**
 * H26, "did custodians leave during the crisis?" (docs/hypotheses-exploratory.md, O1), read from
 * the `departures` and `departure_tests` tables. Every sentence follows the rules of the report's
 * section (src/enron_case/report/departures.py): a suppressed count reads "fewer than k", a
 * p-value is shown only where it is published and otherwise its band.
 */
import {
  DataError,
  type DeparturePeriod,
  type DeparturePeriodRow,
  type DepartureTestRow,
  type PBand,
  type ReleaseData,
} from "@/lib/data";
import { DEPARTURE_PRIMARY, DEPARTURE_SPLITS } from "@/lib/departureVocab";
import { capitalised, formatNumber } from "@/lib/format";
import { minimumGroupSize } from "@/lib/privacy";

/** Outcomes of the decision rule that make the result a finding (docs O1: high or moderate). */
const FINDING_OUTCOMES: ReadonlySet<string> = new Set(["high", "moderate"]);
const SIGNIFICANT_BANDS: ReadonlySet<PBand | null> = new Set<PBand | null>(["below the family bound", "below alpha"]);
const SPLIT_BEFORE: DeparturePeriod = DEPARTURE_SPLITS[0];
const SPLIT_FROM: DeparturePeriod = DEPARTURE_SPLITS[1];
/** Shown where the release publishes neither a p-value nor its band (a window below k). */
const NOT_PUBLISHED = "not published";

/** The run parameters the statement names (config.py), and the minimum group size. */
export interface DepartureSettings {
  k: number;
  alpha: number;
  silenceWeeks: number;
  liveWeeks: number;
  activeWeeks: number;
  lookbackWeeks: number;
  rollingMinAtRisk: number;
  /** Hypotheses stated up to and including H26: the divisor of its family bound. */
  hypothesesStated: number;
}

export interface Departure {
  id: string;
  primary: DepartureTestRow;
  tests: DepartureTestRow[];
  periods: DeparturePeriodRow[];
  settings: DepartureSettings;
  /** The public event the crisis window is split at, as "date (label)". */
  splitEvent: string;
}

function parameter(parameters: Record<string, unknown>, name: string): number {
  const value = parameters[name];
  if (typeof value !== "number" || !Number.isFinite(value)) throw new DataError(`run parameter ${name} is missing`);
  return value;
}

export function periodRow(departure: Pick<Departure, "periods">, name: DeparturePeriod): DeparturePeriodRow {
  const row = departure.periods.find((item) => item.period === name);
  if (!row) throw new DataError(`departures has no row for period "${name}"`);
  return row;
}

function primaryRow(tests: DepartureTestRow[]): DepartureTestRow {
  const row = tests.find((item) => item.variant === DEPARTURE_PRIMARY);
  if (!row) throw new DataError("departure_tests has no primary row");
  return row;
}

function splitEvent(data: ReleaseData, periods: DeparturePeriodRow[]): string {
  const date = periodRow({ periods }, SPLIT_FROM).period_start;
  const event = data.events.find((item) => item.date === date);
  return event ? `${date} (${event.label})` : date;
}

/**
 * H26 from a validated release. It was stated after every other hypothesis, so its number is the
 * count of hypotheses stated up to it (config.HYPOTHESES_STATED).
 */
export function departureFrom(data: ReleaseData, hypothesesStated: number): Departure {
  const { departures: periods, departure_tests: tests } = data.tables;
  const parameters = data.run.parameters;
  return {
    id: `H${hypothesesStated}`,
    primary: primaryRow(tests),
    tests,
    periods,
    settings: {
      k: minimumGroupSize(data),
      alpha: parameter(parameters, "alpha"),
      silenceWeeks: parameter(parameters, "departure_silence_weeks"),
      liveWeeks: parameter(parameters, "departure_live_weeks"),
      activeWeeks: parameter(parameters, "departure_active_weeks"),
      lookbackWeeks: parameter(parameters, "departure_lookback_weeks"),
      rollingMinAtRisk: parameter(parameters, "departure_rolling_min_at_risk"),
      hypothesesStated,
    },
    splitEvent: splitEvent(data, periods),
  };
}

/** True when the decision rule's outcome is a finding (high or moderate confidence). */
export function isFinding(departure: Departure): boolean {
  return departure.primary.outcome !== null && FINDING_OUTCOMES.has(departure.primary.outcome);
}

export function isSignificant(band: PBand | null): boolean {
  return SIGNIFICANT_BANDS.has(band);
}

/** A person count; a suppressed one reads "fewer than k", never a number. */
export function countText(value: number | null, k: number): string {
  return value === null ? `fewer than ${k}` : formatNumber(value);
}

/** The p-value where it is published, otherwise its band. */
export function pText(p: number | null, band: PBand | null, settings: DepartureSettings): string {
  if (p !== null) return `p = ${formatNumber(p, 4)}`;
  const alpha = formatNumber(settings.alpha);
  switch (band) {
    case "below the family bound":
      return `p below ${alpha}/${settings.hypothesesStated}`;
    case "below alpha":
      return `p below ${alpha}`;
    case "alpha or above":
      return `p ${alpha} or above`;
    case "not computable":
      return "p not computable";
    case null:
      return NOT_PUBLISHED;
  }
}

function primaryP(departure: Departure): string {
  return pText(departure.primary.p, departure.primary.p_band, departure.settings);
}

function placeboP(departure: Departure): string {
  return pText(departure.primary.placebo_p, departure.primary.placebo_p_band, departure.settings);
}

/** "d of n at risk", with the share where it is published. */
export function shareText(row: DeparturePeriodRow, k: number): string {
  const text = `${countText(row.departures, k)} of ${countText(row.at_risk, k)} at risk`;
  return row.hazard === null ? text : `${text} (share ${formatNumber(row.hazard)})`;
}

/** The definition, from the run parameters (docs O1, "Definitions"). */
export function departureStatement(settings: DepartureSettings): string {
  return (
    `A custodian at risk at a window's start (sending and receiving in at least ${settings.activeWeeks} of the ` +
    `${settings.lookbackWeeks} weeks before, and not already silent) departs when they send nothing for ` +
    `${settings.silenceWeeks} weeks while, in at least ${settings.liveWeeks} of those weeks, their own mailbox receives mail ` +
    "that only it can hold. If that mail stops too, the silence is a record end: the mailbox was no longer collected, which " +
    "is not a departure."
  );
}

export function evidenceSentence(departure: Departure): string {
  const { k, silenceWeeks } = departure.settings;
  const crisis = periodRow(departure, "crisis");
  const reference = periodRow(departure, "reference");
  return (
    `Custodians who stopped sending for ${silenceWeeks} weeks or more while their own mailbox kept receiving mail: ` +
    `${shareText(crisis, k)} in the crisis window, against ${shareText(reference, k)} in the same weeks a year earlier ` +
    `(one-sided Fisher ${primaryP(departure)}). Record ends: ${countText(crisis.record_ends, k)} in the crisis window, ` +
    `${countText(reference.record_ends, k)} in the reference window.`
  );
}

/** Which necessary conditions of the rule failed, in the order the rule states them. */
export function departureReasons(departure: Departure): string[] {
  const { primary, settings } = departure;
  const crisis = periodRow(departure, "crisis");
  return [
    ...(crisis.departures === null ? [`fewer than ${settings.k} custodians departed in the crisis window`] : []),
    ...(isSignificant(primary.p_band)
      ? []
      : [`the crisis share is not significantly above the same weeks a year earlier (${primaryP(departure)})`]),
    ...(primary.above_rolling ? [] : ["an earlier window of the same length had at least as high a share"]),
    ...(primary.placebo_p_band === "alpha or above" ? [] : [`the pre-crisis placebo does not pass (${placeboP(departure)})`]),
  ];
}

const HIGHER_RATE =
  "custodians stopped sending while their mailbox kept receiving mail at a higher rate in the crisis than";

/** The outcome in plain words, with the reasons when nothing can be established. */
export function departureVerdictSentence(departure: Departure): string {
  const { outcome } = departure.primary;
  if (outcome === "not established" || outcome === null) {
    return `No wave of custodian departures in the crisis can be established: ${departureReasons(departure).join("; ")}.`;
  }
  return (
    `${capitalised(HIGHER_RATE)} in the same weeks a year earlier and than in any comparable earlier window ` +
    `(confidence: ${outcome}).`
  );
}

function leaveOneOut(primary: DepartureTestRow): string {
  if (!isSignificant(primary.p_band)) return "leave-one-out does not apply, since the test itself does not pass.";
  return `leaving each custodian out in turn ${primary.loo_stable ? "keeps" : "does not keep"} the test and the rolling comparison.`;
}

export function rollingSentence(departure: Departure): string {
  const { primary, settings } = departure;
  return (
    `The crisis share is ${primary.above_rolling ? "above" : "not above"} every one of the ${formatNumber(primary.rolling_windows)} ` +
    `earlier windows of the same length with at least ${settings.rollingMinAtRisk} custodians at risk; the pre-crisis placebo ` +
    `has ${placeboP(departure)}; ${leaveOneOut(primary)}`
  );
}

function anySilenceSentence(tests: DepartureTestRow[]): string {
  const outside = tests.find((row) => !row.in_rule);
  if (!outside || outside.p_band === null) return "";
  return (
    ` Counting every silence, record ends included (variant ${outside.variant}), the crisis share is ` +
    `${isSignificant(outside.p_band) ? "" : "still not "}significantly above a year earlier.`
  );
}

/** The robustness variants in the rule, and the one outside it. */
export function variantSentence(departure: Departure): string {
  const ruled = departure.tests.filter((row) => row.in_rule && row.variant !== DEPARTURE_PRIMARY);
  const above = ruled.filter((row) => row.crisis_above_reference === true).length;
  const significant = ruled.filter((row) => isSignificant(row.p_band)).length;
  const hidden = ruled.filter((row) => row.p_band === null).length;
  const hiddenText = hidden
    ? `; ${hidden} ${hidden === 1 ? "publishes" : "publish"} no comparison, because a window has too few custodians at risk`
    : "";
  return (
    `Of the ${ruled.length} robustness variants in the rule, ${above} keep the crisis share above the reference share and ` +
    `${significant} keep p below ${formatNumber(departure.settings.alpha)}${hiddenText}.${anySilenceSentence(departure.tests)}`
  );
}

/** How large a wave the test could see at these numbers at risk, or null where not published. */
export function powerSentence(departure: Departure): string | null {
  const { primary, settings } = departure;
  const crisis = periodRow(departure, "crisis");
  if (primary.detectable_departures === null || crisis.at_risk === null) return null;
  const after = periodRow(departure, "placebo after");
  const placebo =
    primary.placebo_detectable_departures !== null && after.at_risk !== null
      ? `; the placebo would have needed ${formatNumber(primary.placebo_detectable_departures)} of ${formatNumber(after.at_risk)}, so its passing shows little`
      : "";
  return (
    `Even with no departure a year earlier, at least ${formatNumber(primary.detectable_departures)} of the ` +
    `${formatNumber(crisis.at_risk)} custodians at risk would have had to depart in the crisis window for p below ` +
    `${formatNumber(settings.alpha)}, so the test could see only a large wave${placebo}.`
  );
}

/** The crisis window split at a public event; both parts or neither are published. */
export function splitSentence(departure: Departure): string {
  const before = periodRow(departure, SPLIT_BEFORE);
  const from = periodRow(departure, SPLIT_FROM);
  if (before.departures === null || from.departures === null) {
    return (
      `Split at ${departure.splitEvent}, at least one part holds fewer than ${departure.settings.k} departures, so neither ` +
      "is published."
    );
  }
  return (
    `Of the crisis departures, ${formatNumber(before.departures)} began before ${departure.splitEvent} and ` +
    `${formatNumber(from.departures)} from then on.`
  );
}

/**
 * The summary's one sentence on structure: the outcome, and what the test could and could not
 * rule out. `alone` adds "either" when no other hypothesis held up.
 */
export function structureSentence(departure: Departure, alone: boolean): string {
  const { primary } = departure;
  if (primary.outcome !== "not established" && primary.outcome !== null) {
    return `${departure.id}: ${HIGHER_RATE} a year earlier (confidence: ${primary.outcome}).`;
  }
  const crisis = periodRow(departure, "crisis");
  const power =
    primary.detectable_departures !== null && crisis.at_risk !== null
      ? `; the test could only have seen a large wave (at least ${formatNumber(primary.detectable_departures)} of the ` +
        `${formatNumber(crisis.at_risk)} custodians at risk), so a smaller one is not ruled out`
      : "";
  return (
    `No structural change can be established${alone ? " either" : ""}: ${departure.id} asked whether custodians left during ` +
    `the crisis, and no wave of departures can be established${power}.`
  );
}
