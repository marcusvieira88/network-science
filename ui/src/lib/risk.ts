import { RELEASE_VARIANTS, type RiskRow } from "@/lib/data";

export const VARIANT_LABELS: Record<RiskRow["release_variant"], string> = {
  R0: "R0 · pseudonymised edge list (person-level, never published)",
  R1: "R1 · aggregates, k ≥ 5 (published)",
  R2: "R2 · R1 plus noise (sketch)",
};

export const ATTACKER_LABELS: Record<RiskRow["attacker"], string> = {
  A1: "A1 · outsider with the public corpus",
  A2: "A2 · insider with known seeds",
  A3: "A3 · every custodian known (public folder names)",
};

/** The person-level release under pseudonyms, and the published one it is compared with. */
export const PERSON_LEVEL: RiskRow["release_variant"] = "R0";
export const PUBLISHED: RiskRow["release_variant"] = "R1";

type ReidByVariant = { variant: string } & Partial<Record<RiskRow["attacker"], number>>;

/**
 * True for a rate of 0 on a release that holds no person-level record: the attack had nothing to
 * match, so the zero restates the design and is not a measurement.
 */
export function zeroByConstruction(row: RiskRow): boolean {
  return row.release_variant !== PERSON_LEVEL && row.reid_top1 === 0;
}

/** One bar group per release variant, one bar per attacker. */
export function reidByVariant(rows: RiskRow[]): ReidByVariant[] {
  return RELEASE_VARIANTS.map((variant) => {
    const point: ReidByVariant = { variant };
    for (const row of rows) if (row.release_variant === variant && row.reid_top1 !== null) point[row.attacker] = row.reid_top1;
    return point;
  });
}

export interface WorstAttack {
  rate: number;
  targets: number;
}

/** The strongest attacker's re-identification rate against one release, with its target count; null if none ran. */
export function worstReidentification(rows: RiskRow[], variant: RiskRow["release_variant"]): WorstAttack | null {
  let worst: WorstAttack | null = null;
  for (const row of rows) {
    if (row.release_variant !== variant || row.reid_top1 === null) continue;
    if (worst === null || row.reid_top1 > worst.rate) worst = { rate: row.reid_top1, targets: row.n_targets };
  }
  return worst;
}
