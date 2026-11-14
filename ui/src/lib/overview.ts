import type { ReleaseData } from "@/lib/data";
import { formatNumber, formatShare } from "@/lib/format";
import { namedGroups } from "@/lib/network";
import { outsideLabel, outsidePeople } from "@/lib/outside";
import { minimumGroupSize } from "@/lib/privacy";
import { worstReidentification } from "@/lib/risk";
import { analysisWeeks, baselinePeriod } from "@/lib/series";

export interface KeyNumber {
  label: string;
  value: string;
  note: string;
}

/** The strongest attacker's re-identification rate against one release variant, or null if none ran. */
export function worstReid(data: ReleaseData, variant: "R0" | "R1"): number | null {
  return worstReidentification(data.tables.risk, variant)?.rate ?? null;
}

/** The groups card's note: k, and the outside bucket's size apart, since it is not a group. */
function groupsNote(data: ReleaseData): string {
  const note = `each at least ${minimumGroupSize(data)} people`;
  const outside = outsidePeople(data.tables.community_groups);
  if (outside === null) return note;
  return `${note}; ${formatNumber(outside)} more people are ${outsideLabel(baselinePeriod(data)).toLowerCase()}`;
}

/** The published rate is 0 by construction (no person-level record to match), never measured. */
function reidNote(published: number | null): string {
  return published === 0
    ? "strongest attacker; the published tables hold no person to match"
    : "strongest attacker, person-level data vs published";
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
      label: "Weeks analysed",
      value: String(analysisWeeks(data.tables.weekly_metrics).length),
      note: "weekly network snapshots",
    },
    {
      label: "Groups in the network view",
      value: String(namedGroups(data.tables.community_groups).length),
      note: groupsNote(data),
    },
    {
      label: "Re-identification, naive vs published",
      value: `${formatShare(worstReid(data, "R0"))} → ${formatShare(worstReid(data, "R1"))}`,
      note: reidNote(worstReid(data, "R1")),
    },
  ];
}
