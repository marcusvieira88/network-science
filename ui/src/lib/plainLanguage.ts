/**
 * Plain-language readings of the published results, for readers who are not data scientists.
 * Every sentence is built from release fields by the fixed rules below (the same rules the
 * Hypotheses table and the finding card use); nothing here adds a claim the data does not make.
 */
import type { ArtifactCheckRow, ExploratoryRow, HypothesisRow } from "@/lib/data";
import { capitalised, formatNumber, metricLabel } from "@/lib/format";
import { type Departure, departureVerdictSentence, structureSentence } from "@/lib/departures";
import type { HypothesisEntry } from "@/lib/hypotheses";
import { type GroupTie, OTHER_GROUP } from "@/lib/network";

/** What a hypothesis came to, in plain terms. */
export type Verdict = "held" | "artifact" | "weak" | "unclear" | "untestable" | "opposite" | "none" | "withheld";

export const VERDICT_LABELS: Record<Verdict, string> = {
  held: "Held up",
  artifact: "Explained by an artifact",
  weak: "Not robust",
  unclear: "Unclear",
  untestable: "Could not be tested",
  opposite: "Changed the other way",
  none: "No real change",
  withheld: "Withheld",
};

/** Order of the summary bullets: what held up first, then the reasons something did not. */
const SUMMARY_ORDER: readonly Verdict[] = ["artifact", "weak", "unclear", "untestable", "opposite", "none", "withheld"];

/** Caveat prefixes (before the colon) the analysis uses for a test that could not be run validly. */
const UNTESTABLE_PREFIXES: readonly string[] = ["invalid", "untestable"];
const CAVEAT_SEPARATOR = ":";

export interface PlainVerdict {
  verdict: Verdict;
  label: string;
  sentence: string;
}

export interface ExecutiveSummary {
  answer: string;
  points: string[];
}

function verdict(kind: Verdict, sentence: string): PlainVerdict {
  return { verdict: kind, label: VERDICT_LABELS[kind], sentence };
}

function claimOf(row: HypothesisRow): string {
  return `${metricLabel(row.metric)} in the ${row.scope} network`;
}

function preregisteredVerdict(row: HypothesisRow, checks: ArtifactCheckRow[], headline: boolean): PlainVerdict {
  const claim = claimOf(row);
  if (headline) return verdict("held", `${claim} changed, and the change held up under every check.`);
  if (row.supported === "inconclusive") return verdict("unclear", `${claim}: the evidence is mixed.`);
  if (row.supported === "no") return verdict("none", `${claim}: no reliable change.`);
  const failed = checks.find((c) => c.passes === false);
  if (failed) {
    return verdict("artifact", `${claim} looked like a real change, but a check showed a known artifact of the data or the method explains it: ${failed.note}.`);
  }
  if (checks.some((c) => c.passes === null)) {
    return verdict("weak", `${claim} looked like a real change, but the check for a known artifact could not run, so it is not claimed.`);
  }
  return verdict("weak", `${claim} looked like a real change, but it is not robust enough to claim (${row.confidence} confidence).`);
}

/** The reason after "invalid:" or "untestable:", or null for any other caveat. */
export function untestableReason(caveat: string): string | null {
  const separator = caveat.indexOf(CAVEAT_SEPARATOR);
  if (separator < 0) return null;
  const prefix = caveat.slice(0, separator).trim().toLowerCase();
  return UNTESTABLE_PREFIXES.includes(prefix) ? caveat.slice(separator + 1).trim() : null;
}

/**
 * True when the whole interval lies on the side opposite to the prediction: the measure moved,
 * but the other way. "Not supported" then must not read as "no change".
 */
function wentOpposite(row: ExploratoryRow): boolean {
  if (row.ci_low === null || row.ci_high === null) return false;
  return row.direction === "up" ? row.ci_high < 0 : row.ci_low > 0;
}

const OPPOSITE_OF = { up: "down", down: "up" } as const;

function exploratoryVerdict(row: ExploratoryRow): PlainVerdict {
  const measure = row.measure;
  const reason = untestableReason(row.caveat);
  if (reason !== null) return verdict("untestable", `${capitalised(measure)} could not be tested with this data: ${reason}.`);
  const note = row.caveat === "" ? "" : ` (${row.caveat})`;
  switch (row.outcome) {
    case "confident":
      return verdict("held", `${capitalised(measure)} went ${row.direction}, as predicted, and the change held up under every check.`);
    case "inconclusive":
      return verdict("unclear", `The evidence on ${measure} is mixed${note}.`);
    case "not supported":
      if (wentOpposite(row) && row.ci_low !== null && row.ci_high !== null) {
        return verdict(
          "opposite",
          `${capitalised(measure)} did not go ${row.direction} as predicted: it went ${OPPOSITE_OF[row.direction]} (interval ${formatNumber(row.ci_low)} to ${formatNumber(row.ci_high)})${note}.`,
        );
      }
      return verdict("none", `No reliable change in ${measure}${note}.`);
    case null:
      return verdict("withheld", `${capitalised(measure)}: withheld, because too few people were compared to publish it.`);
  }
}

/** H26: a finding (high or moderate) held up; low is a lead, not a finding; else nothing is established. */
function departureVerdict(departure: Departure): PlainVerdict {
  const sentence = departureVerdictSentence(departure);
  switch (departure.primary.outcome) {
    case "high":
    case "moderate":
      return verdict("held", sentence);
    case "low":
      return verdict("weak", sentence);
    case "not established":
    case null:
      return verdict("none", sentence);
  }
}

export function plainVerdict(entry: HypothesisEntry): PlainVerdict {
  switch (entry.kind) {
    case "preregistered":
      return preregisteredVerdict(entry.row, entry.checks, entry.heldTrue);
    case "exploratory":
      return exploratoryVerdict(entry.row);
    case "departure":
      return departureVerdict(entry.departure);
  }
}

/** One bullet per reason, singular or plural; the long tail ("no reliable change") is not listed by id. */
function summaryPoint(kind: Verdict, ids: string[]): string {
  const one = ids.length === 1;
  const named = ` (${ids.join(", ")})`;
  switch (kind) {
    case "artifact":
      return `${ids.length} looked real at first but ${one ? "is explained by a known artifact" : "are explained by known artifacts"} of the data or the method${named}.`;
    case "weak":
      return `${ids.length} looked real but ${one ? "is" : "are"} not robust enough to claim${named}.`;
    case "unclear":
      return `${ids.length} gave mixed evidence${named}.`;
    case "untestable":
      return `${ids.length} could not be tested with this data${named}.`;
    case "opposite":
      return `${ids.length} changed the opposite way to the prediction${named}.`;
    case "none":
      return `${ids.length} showed no reliable change.`;
    case "withheld":
      return `${ids.length} ${one ? "was" : "were"} withheld because too few people were compared.`;
    case "held":
      return `${ids.length} held up${named}.`;
  }
}

/**
 * The one-line answer and the reasons, for the Overview. The behavioural hypotheses are counted by
 * reason; H26, the question about structure, gets a sentence of its own after them.
 */
export function executiveSummary(entries: HypothesisEntry[]): ExecutiveSummary {
  const byVerdict = new Map<Verdict, string[]>();
  for (const entry of entries) {
    if (entry.kind === "departure") continue;
    const kind = plainVerdict(entry).verdict;
    byVerdict.set(kind, [...(byVerdict.get(kind) ?? []), entry.id]);
  }
  const heldBehaviour = byVerdict.get("held") ?? [];
  const held = entries.filter((entry) => plainVerdict(entry).verdict === "held").map((entry) => entry.id);
  const answer =
    held.length === 0
      ? `None of the ${entries.length} hypotheses held up under the checks.`
      : `${held.length} of ${entries.length} hypotheses held up: ${held.join(", ")}.`;
  const points = SUMMARY_ORDER.flatMap((kind) => {
    const ids = byVerdict.get(kind);
    return ids ? [summaryPoint(kind, ids)] : [];
  });
  const structure = entries.flatMap((entry) =>
    entry.kind === "departure" ? [structureSentence(entry.departure, heldBehaviour.length === 0)] : [],
  );
  return { answer, points: [...points, ...structure] };
}

/**
 * The week in one sentence: its busiest link between real groups and how many pairs of real
 * groups exchanged mail. Ties to the outside bucket are left out: it is not a group, and the
 * Network view states its share of the week's mail separately.
 */
export function weekInPlainWords(week: string | null, allTies: readonly GroupTie[]): string {
  if (week === null) return "No week selected.";
  const ties = allTies.filter((tie) => tie.a !== OTHER_GROUP && tie.b !== OTHER_GROUP);
  const [busiest] = ties;
  if (!busiest) return `In the week of ${week} no published mail ran between groups.`;
  return (
    `In the week of ${week} the busiest link between groups was ${busiest.a} ↔ ${busiest.b} ` +
    `(weight ${formatNumber(busiest.total)}); ${ties.length} ${ties.length === 1 ? "pair" : "pairs"} of groups exchanged mail.`
  );
}
