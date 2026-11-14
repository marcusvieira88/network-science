import type { ReleaseData } from "@/lib/data";
import { formatShare } from "@/lib/format";
import { minimumGroupSize } from "@/lib/privacy";
import { analysisWeeks } from "@/lib/series";

export interface KeyNumber {
  label: string;
  value: string;
  note: string;
}

/** The strongest attacker's re-identification rate against one release variant, or null if none ran. */
export function worstReid(data: ReleaseData, variant: "R0" | "R1"): number | null {
  const rates = data.tables.risk.filter((row) => row.release_variant === variant).flatMap((row) => (row.reid_top1 === null ? [] : [row.reid_top1]));
  return rates.length ? Math.max(...rates) : null;
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
      value: String(data.tables.community_groups.length),
      note: `each at least ${minimumGroupSize(data)} people`,
    },
    {
      label: "Re-identification, naive vs published",
      value: `${formatShare(worstReid(data, "R0"))} → ${formatShare(worstReid(data, "R1"))}`,
      note: "strongest attacker, R0 vs R1",
    },
  ];
}
