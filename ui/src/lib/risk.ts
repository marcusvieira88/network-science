import { RELEASE_VARIANTS, type RiskRow } from "@/lib/data";

export const VARIANT_LABELS: Record<RiskRow["release_variant"], string> = {
  R0: "R0 · pseudonymised edge list (before)",
  R1: "R1 · aggregates, k ≥ 5 (published)",
  R2: "R2 · R1 plus noise (sketch)",
};

export const ATTACKER_LABELS: Record<RiskRow["attacker"], string> = {
  A1: "A1 · outsider with the public corpus",
  A2: "A2 · insider with known seeds",
};

type ReidByVariant = { variant: string } & Partial<Record<RiskRow["attacker"], number>>;

/** One bar group per release variant, one bar per attacker: re-identification before and after. */
export function reidByVariant(rows: RiskRow[]): ReidByVariant[] {
  return RELEASE_VARIANTS.map((variant) => {
    const point: ReidByVariant = { variant };
    for (const row of rows) if (row.release_variant === variant && row.reid_top1 !== null) point[row.attacker] = row.reid_top1;
    return point;
  });
}
