/**
 * The executive summary and the chart headlines, in plain words, for readers who will not read the
 * tables. Every number and verdict comes from release fields through the fixed rules below and the
 * verdict rules of plainLanguage.ts; the fixed sentences restate the method and the limits in
 * docs/ and release/report.md, never a result.
 */
import type { DataQualityRow, ExploratoryRow, HeaderFieldRow, Period, ReleaseData, RiskRow, Scope } from "@/lib/data";
import { CONFIDENCE } from "@/lib/data";
import { formatNumber, formatShare, metricLabel } from "@/lib/format";
import { type HypothesisEntry, allHypotheses } from "@/lib/hypotheses";
import { type Verdict, executiveSummary, plainVerdict, untestableReason } from "@/lib/plainLanguage";
import { minimumGroupSize } from "@/lib/privacy";
import { PERSON_LEVEL, PUBLISHED, worstReidentification } from "@/lib/risk";
import { type SeriesPoint, analysisWeeks } from "@/lib/series";
import type { ViewId } from "@/lib/views";

/** Cleaning step names, as written by src/enron_case/release/tables.py (STEP_*). */
const STEPS = {
  parse: "files parsed",
  dedupe: "deduplicate",
  identity: "resolve identities",
  manual: "manual merge check",
  events: "events in the network",
} as const;

/** Header rulings, as in the header allowlist contract. */
const RULING_USABLE = "usable";
const RULING_CONTENT = "content";
const RULING_IDENTIFIER = "identifier";

/** Why the published release's re-identification rate is zero (release/report.md, privacy section). */
const ZERO_BY_DESIGN = "That zero follows from the design: the published tables hold no person-level records for an attack to match";

const SCOPE_PHRASES: Record<Scope, string> = { core: "between custodians", observed: "in the observed network" };

export interface SummaryCard {
  key: "studied" | "found" | "record" | "confidence" | "privacy" | "quality";
  eyebrow: string;
  title: string;
  points: string[];
  view: ViewId;
  linkLabel: string;
}

/** "A", "A and B", "A, B and C". */
export function joinList(items: readonly string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** Counts are whole numbers: no decimals. */
const COUNT_DECIMALS = 0;

function count(value: number): string {
  return formatNumber(value, COUNT_DECIMALS);
}

function step(steps: DataQualityRow[], name: string): DataQualityRow | undefined {
  return steps.find((row) => row.step === name);
}

function entriesOf(data: ReleaseData): HypothesisEntry[] {
  const { hypotheses, exploratory, artifact_checks: checks } = data.tables;
  return allHypotheses(hypotheses, exploratory, checks);
}

function withVerdict(entries: HypothesisEntry[], kind: Verdict): HypothesisEntry[] {
  return entries.filter((entry) => plainVerdict(entry).verdict === kind);
}

function contentFields(fields: HeaderFieldRow[]): string[] {
  return fields.filter((row) => row.ruling === RULING_CONTENT).map((row) => row.field);
}

/** An interval that lies wholly on one side of zero. */
function excludesZero(low: number | null, high: number | null): boolean {
  return low !== null && high !== null && (low > 0 || high < 0);
}

/** An exploratory hypothesis ruled untestable whose measure still moved clearly: the record changed under it. */
function shiftedRecord(entry: HypothesisEntry): entry is HypothesisEntry & { kind: "exploratory"; row: ExploratoryRow } {
  return (
    entry.kind === "exploratory" &&
    plainVerdict(entry).verdict === "untestable" &&
    entry.row.median_change !== null &&
    excludesZero(entry.row.ci_low, entry.row.ci_high)
  );
}

function heldCount(entries: HypothesisEntry[]): number {
  return withVerdict(entries, "held").length;
}

export function studiedCard(data: ReleaseData): SummaryCard {
  const dedupe = step(data.tables.data_quality, STEPS.dedupe);
  const weeks = analysisWeeks(data.tables.weekly_metrics);
  const source = data.run.sample ? "the synthetic sample corpus" : "the public Enron email archive";
  const messages = dedupe ? `${count(dedupe.count_out)} distinct messages from ${source}` : `Messages from ${source}`;
  const span = weeks.length ? `, over ${weeks.length} weeks (weeks of ${weeks[0]} to ${weeks[weeks.length - 1]})` : "";
  const content = contentFields(data.tables.header_fields);
  const contentText = content.length
    ? ` ${joinList(content)} count${content.length === 1 ? "s" : ""} as content and ${content.length === 1 ? "was" : "were"} never stored.`
    : "";
  const events = data.events;
  const eventSpan = events.length ? ` (${events[0]?.date} to ${events[events.length - 1]?.date})` : "";
  return {
    key: "studied",
    eyebrow: "What was studied",
    title: "Who emailed whom, and when, never what was written",
    points: [
      `${messages}${span}.`,
      `Only each message's envelope was analysed: sender, recipients and time.${contentText} Bodies and attachments were never parsed or stored.`,
      `${entriesOf(data).length} hypotheses about how communication changed around ${events.length} public events${eventSpan}, each written down before its result was computed.`,
    ],
    view: "quality",
    linkLabel: "How the data was cleaned",
  };
}

export function foundCard(data: ReleaseData): SummaryCard {
  const { answer, points } = executiveSummary(entriesOf(data));
  return {
    key: "found",
    eyebrow: "What we found",
    title: answer,
    points,
    view: "hypotheses",
    linkLabel: "Every hypothesis in plain words",
  };
}

function shiftSentence(entry: { id: string; row: ExploratoryRow }, data: ReleaseData): string {
  const { row } = entry;
  const { crisis, reference } = data.windows;
  const reason = untestableReason(row.caveat);
  return (
    `${entry.id}, ${row.measure}: within the same ${row.custodians === null ? "" : `${row.custodians} `}custodians it moved by a median of ` +
    `${formatNumber(row.median_change)} (interval ${formatNumber(row.ci_low)} to ${formatNumber(row.ci_high)}) between the reference weeks ` +
    `(${reference.start} to ${reference.end}) and the crisis weeks (${crisis.start} to ${crisis.end}).` +
    (reason === null ? "" : ` It is not read as behaviour: ${reason}.`)
  );
}

function artifactSentence(ids: string[]): string {
  const one = ids.length === 1;
  return (
    `${joinList(ids)} passed ${one ? "its" : "their"} planned statistical tests, but ${one ? "a check shows" : "checks show"} that how ` +
    `the data was collected and analysed explains ${one ? "it" : "them"}, not a detectable change in how people communicated.`
  );
}

/** Measures that moved against the prediction over the same two windows, so the record change may explain them. */
function oppositeSentence(ids: string[]): string {
  const one = ids.length === 1;
  return `${joinList(ids)} moved the other way to the prediction over the same two windows, so the change in the record may explain ${one ? "it" : "them"} too.`;
}

function exploratoryRange(entries: HypothesisEntry[]): string {
  const ids = entries.filter((entry) => entry.kind === "exploratory").map((entry) => entry.id);
  return ids.length > 1 ? `${ids[0]}–${ids[ids.length - 1]}` : joinList(ids);
}

export function recordCard(data: ReleaseData): SummaryCard {
  const entries = entriesOf(data);
  const shifted = entries.filter(shiftedRecord);
  const artifacts = withVerdict(entries, "artifact").map((entry) => entry.id);
  const untestable = withVerdict(entries, "untestable").filter((entry) => !shiftedRecord(entry));
  const opposite = withVerdict(entries, "opposite").map((entry) => entry.id);
  const points = [
    ...shifted.map((entry) => shiftSentence(entry, data)),
    ...(artifacts.length ? [artifactSentence(artifacts)] : []),
    ...untestable.map((entry) => `${entry.id}: ${plainVerdict(entry).sentence}`),
    ...(shifted.length && opposite.length ? [oppositeSentence(opposite)] : []),
    ...(shifted.length
      ? [`Every within-custodian comparison (${exploratoryRange(entries)}) uses these same two windows, so each one compares two ways of keeping the record.`]
      : []),
  ];
  const title =
    shifted.length && heldCount(entries) === 0
      ? "The record changed; no change in behaviour is established"
      : points.length
        ? "Some results reflect how the data was kept"
        : "No result traced back to how the data was kept";
  return { key: "record", eyebrow: "The main finding", title, points, view: "hypotheses", linkLabel: "See the checks behind each result" };
}

function confidenceCounts(entries: HypothesisEntry[]): string | null {
  const levels = entries.flatMap((entry) => (entry.kind === "preregistered" ? [entry.row.confidence] : []));
  if (!levels.length) return null;
  const parts = CONFIDENCE.flatMap((level) => {
    const n = levels.filter((value) => value === level).length;
    return n ? [`${n} ${level}`] : [];
  });
  return `Confidence of the ${levels.length} hypotheses stated before any data: ${parts.join(", ")}.`;
}

function retentionSentence(id: string, row: ExploratoryRow, median: number): string {
  return (
    `${id}, ${row.measure}, ${median >= 0 ? "rose" : "fell"} by a median of ${formatNumber(median)} ` +
    `(interval ${formatNumber(row.ci_low)} to ${formatNumber(row.ci_high)}), but the change is not established once how much ` +
    "inbox mail was kept is accounted for."
  );
}

export function confidenceCard(data: ReleaseData): SummaryCard {
  const entries = entriesOf(data);
  const counts = confidenceCounts(entries);
  const retentionFailed = entries.flatMap((entry) =>
    entry.kind === "exploratory" && entry.row.retention_passes === false && entry.row.median_change !== null
      ? [retentionSentence(entry.id, entry.row, entry.row.median_change)]
      : [],
  );
  return {
    key: "confidence",
    eyebrow: "How sure we are",
    title: "The bar a result had to clear",
    points: [
      "To hold up, a result had to survive a correction for testing many hypotheses at once, repeats that leave out one mailbox at a time, and checks against known quirks of the data.",
      ...(counts === null ? [] : [counts]),
      ...retentionFailed,
      ...(entries.some(shiftedRecord)
        ? ["The pre-crisis placebo tests lie before the change in the record, so they cannot detect it."]
        : []),
    ],
    view: "limits",
    linkLabel: "What the data cannot show",
  };
}

export function privacyCard(data: ReleaseData): SummaryCard {
  const { risk } = data.tables;
  const personLevel = worstReidentification(risk, PERSON_LEVEL);
  const published = worstReidentification(risk, PUBLISHED);
  const attackers = new Set(
    risk.filter((row) => row.release_variant === PERSON_LEVEL && row.reid_top1 !== null).map((row) => row.attacker),
  ).size;
  const points: string[] = [];
  if (personLevel) {
    points.push(
      `From person-level data under pseudonyms (${PERSON_LEVEL}), the strongest of ${attackers} simulated attackers re-identified ` +
        `${formatShare(personLevel.rate)} of ${count(personLevel.targets)} people.`,
    );
  }
  if (published) {
    points.push(
      `From the published release (${PUBLISHED}), which holds only groups of at least ${minimumGroupSize(data)} people, ` +
        `the strongest re-identified ${formatShare(published.rate)}.`,
    );
    if (published.rate === 0) {
      points.push(
        `${ZERO_BY_DESIGN}, so it is not a measurement of every remaining risk.`,
      );
    }
  }
  points.push("No attack on the published group tables themselves was run.");
  return { key: "privacy", eyebrow: "Privacy", title: "Pseudonymised is not anonymous", points, view: "risk", linkLabel: "See the attacks" };
}

function identitySentence(identity: DataQualityRow): string {
  const measured =
    identity.precision !== null && identity.recall !== null
      ? `; against known answers, precision is ${formatShare(identity.precision)} and recall ${formatShare(identity.recall)}`
      : "";
  return `${count(identity.count_in)} addresses were merged into ${count(identity.count_out)} identities by documented rules${measured}.`;
}

function manualSentence(manual: DataQualityRow): string | null {
  if (manual.precision === null) return null;
  const interval =
    manual.precision_ci_low !== null && manual.precision_ci_high !== null
      ? ` (interval ${formatShare(manual.precision_ci_low)} to ${formatShare(manual.precision_ci_high)})`
      : "";
  return `A person checked ${count(manual.count_in)} sampled merges and judged ${formatShare(manual.precision)} of them correct${interval}.`;
}

export function qualityCard(data: ReleaseData): SummaryCard {
  const steps = data.tables.data_quality;
  const parse = step(steps, STEPS.parse);
  const dedupe = step(steps, STEPS.dedupe);
  const identity = step(steps, STEPS.identity);
  const manual = step(steps, STEPS.manual);
  const events = step(steps, STEPS.events);
  const points = [
    parse ? `${count(parse.count_out)} of ${count(parse.count_in)} files could be read.` : null,
    dedupe ? `Removing ${count(dedupe.removed)} stored copies left ${count(dedupe.count_out)} distinct messages.` : null,
    identity ? identitySentence(identity) : null,
    manual ? manualSentence(manual) : null,
    events
      ? `${count(events.count_out)} of ${count(events.count_in)} sender–recipient links entered the network; the rest belong to messages flagged out of it, such as mass mailings.`
      : null,
  ].filter((point): point is string => point !== null);
  return {
    key: "quality",
    eyebrow: "Data quality",
    title: "Cleaned by documented rules, with measured error",
    points,
    view: "quality",
    linkLabel: "See every cleaning step",
  };
}

export function summaryCards(data: ReleaseData): SummaryCard[] {
  return [studiedCard(data), foundCard(data), recordCard(data), confidenceCard(data), privacyCard(data), qualityCard(data)];
}

/** "What this means for a real organisation": each lesson tied to this release's own numbers. */
export function whatItMeans(data: ReleaseData): string[] {
  const entries = entriesOf(data);
  const traced = entries
    .filter((entry) => ["artifact", "untestable"].includes(plainVerdict(entry).verdict))
    .map((entry) => entry.id);
  const held = heldCount(entries);
  const notHeld = entries.length - held;
  const personLevel = worstReidentification(data.tables.risk, PERSON_LEVEL);
  const content = contentFields(data.tables.header_fields);
  return [
    ...(traced.length
      ? [
          `Check how the data was kept before reading behaviour into it: here ${traced.length} of ${entries.length} results trace back to how the data was collected or analysed (${traced.join(", ")}).`,
        ]
      : []),
    `Fix the questions and checks before looking at results, label any check added later, and publish every outcome: all ${entries.length} hypotheses are published here, ` +
      (held === 0 ? "though none held up." : `including the ${notHeld} that did not hold up.`),
    ...(personLevel
      ? [
          `Treat pseudonymised person-level data as identifiable: a simulated attacker re-identified ${formatShare(personLevel.rate)} of people from it here. ` +
            `Share only groups of at least ${minimumGroupSize(data)} people.`,
        ]
      : []),
    "This kind of question can be studied without reading content: only sender, recipients and time were used" +
      (content.length ? `, and ${joinList(content)} ${content.length === 1 ? "was" : "were"} never stored.` : "."),
    "Before applying this to your own staff's email: collect header fields only at the source, keep the pseudonymisation key in your own key store, replace the noise sketch with a formal privacy budget, and agree the questions and thresholds with employee representatives, such as a works council, first.",
  ];
}

/** The chart's headline: the week the selected series peaked (the earliest, if several tie). */
export function metricHeadline(series: SeriesPoint[], metric: string, scope: Scope): string {
  const subject = `${metricLabel(metric)} ${SCOPE_PHRASES[scope]}`;
  let peak: { week: string; value: number } | null = null;
  for (const point of series) {
    if (point.value !== null && (peak === null || point.value > peak.value)) peak = { week: point.week, value: point.value };
  }
  if (peak === null) return `${subject}: every week of this selection is hidden.`;
  return `${subject} peaked in the week of ${peak.week} at ${formatNumber(peak.value)}.`;
}

/** How to read the metric chart. */
export function metricCaption(baseline: Period | null): string {
  const band = baseline ? `The shaded band is the baseline period, ${baseline.start} to ${baseline.end}; numbered` : "Numbered";
  return (
    `Each point is one week. ${band} dashed lines mark the public events listed below; gaps are weeks hidden because too few ` +
    "people were active to publish them. The archive kept more mail in some periods than in others, so a rise can reflect what was " +
    "kept, not only how much people wrote."
  );
}

/** The risk chart's headline, or null when either release was not attacked. */
export function riskHeadline(rows: RiskRow[]): string | null {
  const personLevel = worstReidentification(rows, PERSON_LEVEL);
  const published = worstReidentification(rows, PUBLISHED);
  if (personLevel === null || published === null) return null;
  return (
    `The strongest attack re-identified ${formatShare(personLevel.rate)} of people from person-level data (${PERSON_LEVEL}); ` +
    `the strongest against the published release (${PUBLISHED}), ${formatShare(published.rate)}.` +
    (published.rate === 0 ? ` ${ZERO_BY_DESIGN}.` : "")
  );
}

/** The cleaning funnel's headline, or null when the deduplication step is not in the release. */
export function funnelHeadline(steps: DataQualityRow[]): string | null {
  const dedupe = step(steps, STEPS.dedupe);
  if (!dedupe) return null;
  return `Of ${count(dedupe.count_in)} stored copies, ${count(dedupe.count_out)} distinct messages remain after removing duplicates.`;
}

/** The header ruling's headline: what is kept and what is never stored. */
export function headerHeadline(fields: HeaderFieldRow[]): string {
  const usable = fields.filter((row) => row.ruling === RULING_USABLE).map((row) => row.field);
  const identifiers = fields.filter((row) => row.ruling === RULING_IDENTIFIER).length;
  const content = contentFields(fields);
  const parts = [
    usable.length ? `${joinList(usable)} ${usable.length === 1 ? "is" : "are"} kept as metadata` : "none is kept as metadata",
    ...(identifiers
      ? [`${identifiers} identifier field${identifiers === 1 ? " is" : "s are"} replaced by pseudonyms or discarded at ingest`]
      : []),
    ...(content.length ? [`${joinList(content)} ${content.length === 1 ? "is" : "are"} content and never stored`] : []),
  ];
  return `Of ${fields.length} header fields, ${parts.join("; ")}.`;
}
