/**
 * The UI's own privacy guard, mirroring the export's refusal rules (uiexport/export.py):
 * no address, no person or organisation pseudonym, no person count below k, and no H26 cell that
 * reveals a group below k by subtraction.
 */
import type { DeparturePeriodRow, ReleaseData } from "@/lib/data";
import { DEPARTURE_PRIMARY, DEPARTURE_SPLITS, DEPARTURE_WINDOWS } from "@/lib/departureVocab";

/** Same patterns as LEAK_PATTERNS in src/enron_case/contracts/vocab.py. */
export const LEAK_PATTERN = /@|p_[a-z2-7]{16}|o_[a-z2-7]{16}/;

/** The release's smallest publishable group; never trust a data file to lower it. */
const K_FLOOR = 5;

/** Release columns that count persons (PERSON_COUNT_COLUMNS in contracts/schemas.py). */
export const PERSON_COUNT_COLUMNS = {
  weekly_metrics: ["n_active"],
  risk: ["n_targets"],
  degree_distribution: ["persons"],
  community_groups: ["n_persons"],
  exploratory: ["custodians", "placebo_custodians"],
  departures: ["at_risk", "departures", "record_ends"],
} as const;

/** The crisis window and its two parts. */
const CRISIS_PARTS: readonly DeparturePeriodRow["period"][] = [DEPARTURE_WINDOWS[0], ...DEPARTURE_SPLITS];
const SPLIT_COUNTS = ["departures", "record_ends"] as const;

/** The weekly metric whose value is itself a person count (PERSON_COUNT_METRIC in schemas.py). */
const PERSON_COUNT_METRIC = "active_persons";

export class PrivacyError extends Error {
  override name = "PrivacyError";
}

function* strings(value: unknown): Generator<string> {
  if (typeof value === "string") {
    yield value;
  } else if (Array.isArray(value)) {
    for (const item of value) yield* strings(item);
  } else if (typeof value === "object" && value !== null) {
    for (const [key, item] of Object.entries(value)) {
      yield key;
      yield* strings(item);
    }
  }
}

export function minimumGroupSize(data: ReleaseData): number {
  const kMin = data.run.parameters.k_min;
  return typeof kMin === "number" ? Math.max(kMin, K_FLOOR) : K_FLOOR;
}

export function identifierCount(value: unknown): number {
  let hits = 0;
  for (const text of strings(value)) if (LEAK_PATTERN.test(text)) hits += 1;
  return hits;
}

export function smallPersonCounts(data: ReleaseData): number {
  const k = minimumGroupSize(data);
  let small = 0;
  for (const [table, columns] of Object.entries(PERSON_COUNT_COLUMNS)) {
    const rows = data.tables[table as keyof typeof PERSON_COUNT_COLUMNS] as Record<string, unknown>[];
    for (const row of rows) {
      for (const column of columns) {
        const count = row[column];
        if (typeof count === "number" && count < k) small += 1;
      }
    }
  }
  for (const row of data.tables.weekly_metrics) {
    if (row.metric === PERSON_COUNT_METRIC && row.value !== null && row.value < k) small += 1;
  }
  return small;
}

function smallComplements(row: DeparturePeriodRow, k: number): boolean {
  const { at_risk: atRisk, departures, record_ends: ends } = row;
  if (atRisk === null) return false;
  const complements = [
    departures === null ? null : atRisk - departures,
    ends === null ? null : atRisk - ends,
    departures === null || ends === null ? null : atRisk - departures - ends,
  ];
  return complements.some((value) => value !== null && value < k);
}

/** Two of the crisis total and its two parts give the third by subtraction. */
function revealingSplits(rows: DeparturePeriodRow[]): number {
  const parts = rows.filter((row) => CRISIS_PARTS.includes(row.period));
  return SPLIT_COUNTS.filter((column) => parts.filter((row) => row[column] !== null).length === 2).length;
}

/**
 * H26 cells that would reveal a group below k though no count in them is below k (release/kanon.py
 * and release/tables.py): a complement in its row (at risk minus a count), a share published for a
 * suppressed count, a crisis split two of whose counts give the third, and a p-value or power count
 * for a robustness variant, whose counts are nested in the primary's.
 */
export function departureDisclosures(data: ReleaseData): number {
  const k = minimumGroupSize(data);
  const periods = data.tables.departures;
  const complements = periods.filter((row) => smallComplements(row, k)).length;
  const shares = periods.filter((row) => row.hazard !== null && (row.departures === null || row.at_risk === null)).length;
  const variants = data.tables.departure_tests.filter(
    (row) =>
      row.variant !== DEPARTURE_PRIMARY &&
      [row.p, row.placebo_p, row.detectable_departures, row.placebo_detectable_departures].some((value) => value !== null),
  ).length;
  return complements + shares + revealingSplits(periods) + variants;
}

export function assertReleasePrivacy(data: ReleaseData): void {
  const identifiers = identifierCount(data);
  if (identifiers) throw new PrivacyError(`release data holds ${identifiers} identifier-shaped values`);
  const small = smallPersonCounts(data);
  if (small) throw new PrivacyError(`release data holds ${small} person counts below the minimum group size`);
  const disclosures = departureDisclosures(data);
  if (disclosures) throw new PrivacyError(`release data holds ${disclosures} departure cells that reveal a group below the minimum size`);
}
