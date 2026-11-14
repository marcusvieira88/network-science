import type { ReleaseData, RiskRow } from "@/lib/data";
import { formatNumber, formatShare } from "@/lib/format";
import { namedGroups } from "@/lib/network";
import { outsideLabel, outsidePeople } from "@/lib/outside";
import { minimumGroupSize } from "@/lib/privacy";
import { PERSON_LEVEL, PUBLISHED, worstReidentification } from "@/lib/risk";
import { analysisWeeks, baselinePeriod } from "@/lib/series";

export interface KeyNumber {
  label: string;
  value: string;
  note: string;
}

/** The strongest attacker's re-identification rate against one release variant, or null if none ran. */
export function worstReid(data: ReleaseData, variant: RiskRow["release_variant"]): number | null {
  return worstReidentification(data.tables.risk, variant)?.rate ?? null;
}

/** The groups card's note: k, and the outside bucket's size apart, since it is not a group. */
function groupsNote(data: ReleaseData): string {
  const note = `each at least ${minimumGroupSize(data)} people`;
  const outside = outsidePeople(data.tables.community_groups);
  if (outside === null) return note;
  return `${note}; ${formatNumber(outside)} more internal people are ${outsideLabel(baselinePeriod(data)).toLowerCase()}`;
}

/**
 * Only the person-level data was measured. A published rate of 0 is by construction (no
 * person-level record to match), so it is stated as that, never drawn as a measured drop.
 */
function reidNote(published: number | null): string {
  if (published === null) return `strongest attacker, on ${PERSON_LEVEL}, which is never published`;
  if (published === 0) {
    return (
      `strongest attacker, on ${PERSON_LEVEL}, which is never published; the published tables hold no ` +
      "person-level record, so the attack does not apply to them (0 by construction, not a measurement)"
    );
  }
  return `strongest attacker, on ${PERSON_LEVEL}, which is never published; ${formatShare(published)} against the published release`;
}

export function keyNumbers(data: ReleaseData): KeyNumber[] {
  const steps = data.tables.data_quality;
  const dedupe = steps.find((row) => row.step.toLowerCase().includes("dedup"));
  return [
    {
      label: "Messages after deduplication",
      value: dedupe ? dedupe.count_out.toLocaleString("en-US") : "n/a",
      note: dedupe ? `from ${dedupe.count_in.toLocaleString("en-US")} stored copies` : "step not in release",
    },
    {
      label: "Weeks in the weekly series",
      value: String(analysisWeeks(data.tables.weekly_metrics).length),
      note: "weekly network snapshots, by the Monday each week begins",
    },
    {
      label: "Groups in the network view",
      value: String(namedGroups(data.tables.community_groups).length),
      note: groupsNote(data),
    },
    {
      label: "Re-identified from person-level data",
      value: formatShare(worstReid(data, PERSON_LEVEL)),
      note: reidNote(worstReid(data, PUBLISHED)),
    },
  ];
}
