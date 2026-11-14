/**
 * The UI's own privacy guard, mirroring the export's refusal rules (uiexport/export.py):
 * no address, no person or organisation pseudonym, no person count below k.
 */
import type { ReleaseData } from "@/lib/data";

/** Same patterns as LEAK_PATTERNS in src/enron_case/contracts/vocab.py. */
export const LEAK_PATTERN = /@|p_[a-z2-7]{16}|o_[a-z2-7]{16}/;

/** The release's smallest publishable group; never trust a data file to lower it. */
export const K_FLOOR = 5;

/** Release columns that count persons (PERSON_COUNT_COLUMNS in contracts/schemas.py). */
export const PERSON_COUNT_COLUMNS = {
  weekly_metrics: ["n_active"],
  risk: ["n_targets"],
  degree_distribution: ["persons"],
  community_groups: ["n_persons"],
  exploratory: ["custodians", "placebo_custodians"],
} as const;

/** The weekly metric whose value is itself a person count (PERSON_COUNT_METRIC in schemas.py). */
export const PERSON_COUNT_METRIC = "active_persons";

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

export function assertReleasePrivacy(data: ReleaseData): void {
  const identifiers = identifierCount(data);
  if (identifiers) throw new PrivacyError(`release data holds ${identifiers} identifier-shaped values`);
  const small = smallPersonCounts(data);
  if (small) throw new PrivacyError(`release data holds ${small} person counts below the minimum group size`);
}
