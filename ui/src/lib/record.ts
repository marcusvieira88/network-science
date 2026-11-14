/**
 * The finding about the record: whether the release shows that the way the `Date` header was
 * recorded changed between the reference and the crisis windows, and how sure that is. The rule is
 * the report's (src/enron_case/report/record.py, CONFIDENCE_RULE), applied to the same release
 * tables: `record_profile` and the within-custodian after-hours hypothesis.
 */
import type { Period, RecordProfileRow, ReleaseData } from "@/lib/data";
import { excludesZero } from "@/lib/plainLanguage";

/** The within-custodian after-hours share: its estimate measures the record (TIMESTAMP_HYPOTHESIS in record.py). */
export const TIMESTAMP_HYPOTHESIS = "H5";

export type RecordConfidence = "high" | "moderate";

const MONTH_START = "-01";
const MONTH_LENGTH = 7;

/** The first day of an ISO date's month. */
function monthOf(date: string): string {
  return `${date.slice(0, MONTH_LENGTH)}${MONTH_START}`;
}

/**
 * Published after-hours shares of the months from the window's first month up to, not including,
 * the month holding its end: August to November for a window from mid-August to early December.
 */
export function windowShares(profile: RecordProfileRow[], window: Period): number[] {
  const first = monthOf(window.start);
  const last = monthOf(window.end);
  return profile.flatMap((row) =>
    row.month >= first && row.month < last && row.after_hours_share !== null ? [row.after_hours_share] : [],
  );
}

/** True when every crisis month lies below every reference month, false when above; null when the ranges overlap. */
function movedLower(reference: number[], crisis: number[]): boolean | null {
  if (Math.max(...crisis) < Math.min(...reference)) return true;
  return Math.min(...crisis) > Math.max(...reference) ? false : null;
}

/**
 * High when the monthly ranges of the two windows do not overlap and the change within the same
 * people has an interval that excludes zero; moderate when the ranges do not
 * overlap but that change is not measured or its interval includes zero; null when no change of
 * the record is claimed (overlapping ranges, or too few published months).
 */
export function recordConfidence(data: ReleaseData): RecordConfidence | null {
  const profile = data.tables.record_profile;
  const reference = windowShares(profile, data.windows.reference);
  const crisis = windowShares(profile, data.windows.crisis);
  if (!reference.length || !crisis.length) return null;
  if (movedLower(reference, crisis) === null) return null;
  const row = data.tables.exploratory.find((candidate) => candidate.hypothesis === TIMESTAMP_HYPOTHESIS);
  const measured = row !== undefined && row.median_change !== null;
  return measured && excludesZero(row.ci_low, row.ci_high) ? "high" : "moderate";
}

/** The finding in one sentence, the same on every surface; null when no change of the record is claimed. */
export function recordFinding(data: ReleaseData): string | null {
  const confidence = recordConfidence(data);
  if (confidence === null) return null;
  return `The finding: the record changed (${confidence} confidence that it changed; cause not established).`;
}

/** What is not claimed, next to the finding about the record. */
export const NO_BEHAVIOURAL_FINDING = "No behavioural finding about the crisis year is claimed.";
