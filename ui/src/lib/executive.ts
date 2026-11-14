/**
 * The executive summary and the chart headlines, in plain words, for readers who will not read the
 * tables. Every number and verdict comes from release fields through the fixed rules below and the
 * verdict rules of plainLanguage.ts; the fixed sentences restate the method and the limits in
 * docs/ and release/report.md, never a result.
 */
import type { DataQualityRow, ExploratoryRow, HeaderFieldRow, Period, ReleaseData, RiskRow, Scope } from "@/lib/data";
import { CONFIDENCE } from "@/lib/data";
import { formatNumber, formatShare, joinList, metricLabel } from "@/lib/format";

export { joinList };
import { type HypothesisEntry, TIMING_LABELS, countByTiming, placeboShowsChange, releaseHypotheses } from "@/lib/hypotheses";
import { namedGroups } from "@/lib/network";
import { outsideLabel, outsidePeople } from "@/lib/outside";
import { type Verdict, executiveSummary, isRecordEvidence, plainVerdict, untestableReason } from "@/lib/plainLanguage";
import { minimumGroupSize } from "@/lib/privacy";
import { NO_BEHAVIOURAL_FINDING, recordFinding } from "@/lib/record";
import { PERSON_LEVEL, PUBLISHED, worstReidentification } from "@/lib/risk";
import { type SeriesPoint, analysisWeeks, baselinePeriod } from "@/lib/series";
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

/** The count of occurrences of names without a ruling; not a header field (vocab.OTHER_HEADER_FIELD). */
const OTHER_HEADER_FIELD = "(other)";

const SCOPE_PHRASES: Record<Scope, string> = { core: "between custodians", observed: "in the observed network" };

export interface SummaryCard {
  key: "studied" | "found" | "record" | "confidence" | "privacy" | "quality";
  eyebrow: string;
  title: string;
  points: string[];
  view: ViewId;
  linkLabel: string;
}

/** Counts are whole numbers: no decimals. */
const COUNT_DECIMALS = 0;

function count(value: number): string {
  return formatNumber(value, COUNT_DECIMALS);
}

function step(steps: DataQualityRow[], name: string): DataQualityRow | undefined {
  return steps.find((row) => row.step === name);
}

function withVerdict(entries: HypothesisEntry[], kind: Verdict): HypothesisEntry[] {
  return entries.filter((entry) => plainVerdict(entry).verdict === kind);
}

function contentFields(fields: HeaderFieldRow[]): string[] {
  return fields.filter((row) => row.ruling === RULING_CONTENT).map((row) => row.field);
}

/** An exploratory hypothesis ruled untestable whose measure still moved clearly: the record changed under it. */
function shiftedRecord(entry: HypothesisEntry): entry is HypothesisEntry & { kind: "exploratory"; row: ExploratoryRow } {
  return entry.kind === "exploratory" && isRecordEvidence(entry.row);
}

function heldCount(entries: HypothesisEntry[]): number {
  return withVerdict(entries, "held").length;
}

/** H26 asks about structure (who left), not about how people communicated. */
function behaviouralHeldCount(entries: HypothesisEntry[]): number {
  return withVerdict(entries, "held").filter((entry) => entry.kind !== "departure").length;
}

/**
 * The weekly series' span. Weeks begin on a Monday, so a first week that starts before the
 * analysis does is partial; the messages are not all inside these weeks, so they are counted apart.
 */
function seriesSentence(weeks: string[], analysisStart: unknown): string | null {
  const [first] = weeks;
  const last = weeks[weeks.length - 1];
  if (first === undefined || last === undefined) return null;
  const partial = typeof analysisStart === "string" && first < analysisStart ? "; the first week is partial" : "";
  return `The weekly network series has ${weeks.length} weeks, beginning on the Mondays ${first} to ${last}${partial}.`;
}

export function studiedCard(data: ReleaseData): SummaryCard {
  const dedupe = step(data.tables.data_quality, STEPS.dedupe);
  const source = data.run.sample ? "the synthetic sample corpus" : "the public Enron email archive";
  const messages = dedupe ? `${count(dedupe.count_out)} distinct messages from ${source}` : `Messages from ${source}`;
  const series = seriesSentence(analysisWeeks(data.tables.weekly_metrics), data.run.parameters.analysis_start);
  const content = contentFields(data.tables.header_fields);
  const contentText = content.length
    ? ` ${joinList(content)} count${content.length === 1 ? "s" : ""} as content and ${content.length === 1 ? "was" : "were"} never stored.`
    : "";
  const events = data.events;
  const eventSpan = events.length ? ` (${events[0]?.date} to ${events[events.length - 1]?.date})` : "";
  const entries = releaseHypotheses(data);
  const timing = countByTiming(entries);
  return {
    key: "studied",
    eyebrow: "What was studied",
    title: "Who emailed whom, and when, never what was written",
    points: [
      `${messages}.${series === null ? "" : ` ${series}`}`,
      `Only each message's envelope was analysed: sender, recipients and time.${contentText} Bodies and attachments were never decoded, parsed or stored.`,
      `${entries.length} hypotheses about how communication, and who took part in it, changed around ${events.length} public events${eventSpan}. ` +
        `Each was written down before its own result was computed: ${timing.preregistered} ${TIMING_LABELS.preregistered}, ` +
        `${timing.stated} ${TIMING_LABELS.stated}, ${timing.postHoc} ${TIMING_LABELS.postHoc}.`,
    ],
    view: "quality",
    linkLabel: "How the data was cleaned",
  };
}

export function foundCard(data: ReleaseData): SummaryCard {
  const { answer, points } = executiveSummary(releaseHypotheses(data));
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
    (reason === null
      ? ""
      : ` It is not read as behaviour: ${reason}. As a claim about behaviour ${entry.id} could not be tested; the same number is read here as a measurement of the record.`)
  );
}

function artifactSentence(ids: string[]): string {
  const one = ids.length === 1;
  return (
    `${joinList(ids)} passed ${one ? "its" : "their"} planned statistical tests, but ${one ? "a check shows" : "checks show"} that how ` +
    `the data was collected and analysed explains ${one ? "it" : "them"}, not a detectable change in how people communicated.`
  );
}

/**
 * Measures that moved against the prediction over the same two windows. The change in the record
 * may explain them, except where the pre-crisis placebo, which lies before that change, already
 * shows the same move.
 */
function oppositeSentences(entries: HypothesisEntry[]): string[] {
  const opposite = withVerdict(entries, "opposite");
  const before = opposite.filter((entry) => entry.kind === "exploratory" && placeboShowsChange(entry.row)).map((entry) => entry.id);
  const open = opposite.map((entry) => entry.id).filter((id) => !before.includes(id));
  const one = open.length === 1;
  return [
    ...(open.length
      ? [`${joinList(open)} moved the other way to the prediction over the same two windows, so the change in the record may explain ${one ? "it" : "them"} too.`]
      : []),
    ...(before.length
      ? [
          `${joinList(before)} moved the other way too, but the comparison before the crisis, which lies before the change in the record, already shows the same move, so that change does not explain ${before.length === 1 ? "it" : "them"}.`,
        ]
      : []),
  ];
}

function exploratoryRange(entries: HypothesisEntry[]): string {
  const ids = entries.filter((entry) => entry.kind === "exploratory").map((entry) => entry.id);
  return ids.length > 1 ? `${ids[0]}–${ids[ids.length - 1]}` : joinList(ids);
}

/**
 * The finding about the record and, only when no behavioural hypothesis is held, the sentence
 * saying so; null when no change of the record is claimed. One line for every surface.
 */
export function recordFindingLine(data: ReleaseData): string | null {
  const finding = recordFinding(data);
  if (finding === null) return null;
  return behaviouralHeldCount(releaseHypotheses(data)) === 0 ? `${finding} ${NO_BEHAVIOURAL_FINDING}` : finding;
}

export function recordCard(data: ReleaseData): SummaryCard {
  const entries = releaseHypotheses(data);
  const shifted = entries.filter(shiftedRecord);
  const artifacts = withVerdict(entries, "artifact").map((entry) => entry.id);
  const untestable = withVerdict(entries, "untestable").filter((entry) => !shiftedRecord(entry));
  const finding = recordFindingLine(data);
  const noBehaviour = behaviouralHeldCount(entries) === 0;
  const points = [
    ...(finding === null ? [] : [finding]),
    ...shifted.map((entry) => shiftSentence(entry, data)),
    ...(artifacts.length ? [artifactSentence(artifacts)] : []),
    ...untestable.map((entry) => `${entry.id}: ${plainVerdict(entry).sentence}`),
    ...(shifted.length ? oppositeSentences(entries) : []),
    ...(shifted.length
      ? [`Every within-custodian comparison (${exploratoryRange(entries)}) uses these same two windows, so each one compares two ways of keeping the record.`]
      : []),
  ];
  const title =
    finding !== null && noBehaviour
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
  return `Confidence of the ${levels.length} ${TIMING_LABELS.preregistered} hypotheses: ${parts.join(", ")}.`;
}

function retentionSentence(id: string, row: ExploratoryRow, median: number): string {
  return (
    `${id}, ${row.measure}, ${median >= 0 ? "rose" : "fell"} by a median of ${formatNumber(median)} ` +
    `(interval ${formatNumber(row.ci_low)} to ${formatNumber(row.ci_high)}), but the change is not established once how much ` +
    "inbox mail was kept is accounted for."
  );
}

export function confidenceCard(data: ReleaseData): SummaryCard {
  const entries = releaseHypotheses(data);
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

/** A published rate of 0: the design, stated as that and never as a measured result. */
function zeroByDesign(k: number): string {
  return (
    `The published release (${PUBLISHED}) holds only groups of at least ${k} people and no person-level record, so these attacks ` +
    "have nothing to match there: its rate of 0% is by construction, not a measurement."
  );
}

export function privacyCard(data: ReleaseData): SummaryCard {
  const { risk } = data.tables;
  const personLevel = worstReidentification(risk, PERSON_LEVEL);
  const published = worstReidentification(risk, PUBLISHED);
  const attackers = new Set(
    risk.filter((row) => row.release_variant === PERSON_LEVEL && row.reid_top1 !== null).map((row) => row.attacker),
  ).size;
  const k = minimumGroupSize(data);
  const points: string[] = [];
  if (personLevel) {
    points.push(
      `From person-level data under pseudonyms (${PERSON_LEVEL}, never published), the strongest of ${attackers} simulated attackers re-identified ` +
        `${formatShare(personLevel.rate)} of the ${count(personLevel.targets)} people it targeted.`,
    );
  }
  if (published) {
    points.push(
      published.rate === 0
        ? zeroByDesign(k)
        : `Against the published release (${PUBLISHED}), which holds only groups of at least ${k} people, the strongest re-identified ${formatShare(published.rate)}.`,
    );
  }
  points.push("No attack on the published group tables themselves was run.");
  return { key: "privacy", eyebrow: "Privacy", title: "Pseudonymised is not anonymous", points, view: "risk", linkLabel: "See the attacks" };
}

function identitySentence(identity: DataQualityRow): string {
  const measured =
    identity.precision !== null && identity.recall !== null
      ? `; against the known answers of the synthetic corpus, precision is ${formatShare(identity.precision)} and recall ${formatShare(identity.recall)}`
      : "";
  return `${count(identity.count_in)} addresses were merged into ${count(identity.count_out)} identities by documented rules${measured}.`;
}

function manualSentence(manual: DataQualityRow): string | null {
  if (manual.precision === null) return null;
  const interval =
    manual.precision_ci_low !== null && manual.precision_ci_high !== null
      ? ` (interval ${formatShare(manual.precision_ci_low)} to ${formatShare(manual.precision_ci_high)})`
      : "";
  return (
    `A person checked ${count(manual.count_in)} sampled merges and judged ${formatShare(manual.precision)} of them correct${interval}. ` +
    "That sample gives no recall; precision and recall against known answers exist for the synthetic corpus only."
  );
}

/**
 * Why the counts of people differ from view to view: each has its own base. Null unless at least
 * two of the bases are in the release.
 */
export function peopleBases(data: ReleaseData): string | null {
  const identity = step(data.tables.data_quality, STEPS.identity);
  const attacked = worstReidentification(data.tables.risk, PERSON_LEVEL);
  const groups = data.tables.community_groups;
  const grouped = namedGroups(groups).reduce((sum, group) => sum + group.n_persons, 0);
  const outside = outsidePeople(groups);
  const label = outsideLabel(baselinePeriod(data)).toLowerCase();
  const parts = [
    identity ? `${count(identity.count_out)} identities are every address owner in the corpus after merging` : null,
    attacked ? `${count(attacked.targets)} are the people in the observed network that the strongest attack targeted` : null,
    grouped > 0
      ? `${count(grouped)} internal people are in a published group` + (outside === null ? "" : ` and ${count(outside)} are ${label}`)
      : null,
  ].filter((part): part is string => part !== null);
  return parts.length < 2 ? null : `The counts of people have different bases: ${parts.join("; ")}.`;
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
    peopleBases(data),
  ].filter((point): point is string => point !== null);
  return {
    key: "quality",
    eyebrow: "Data quality",
    title: "Cleaned by documented rules, checked on a sample",
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
  const entries = releaseHypotheses(data);
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

/** The risk chart's headline, or null when either release has no row. */
export function riskHeadline(rows: RiskRow[]): string | null {
  const personLevel = worstReidentification(rows, PERSON_LEVEL);
  const published = worstReidentification(rows, PUBLISHED);
  if (personLevel === null || published === null) return null;
  const measured = `The strongest attack re-identified ${formatShare(personLevel.rate)} of people from person-level data (${PERSON_LEVEL}), which is never published`;
  if (published.rate === 0) {
    return (
      `${measured}. The published release (${PUBLISHED}) holds no person-level record, so these attacks have nothing to match there: ` +
      "its 0% is by construction, not a measurement."
    );
  }
  return `${measured}; against the published release (${PUBLISHED}), the strongest reached ${formatShare(published.rate)}.`;
}

/** The cleaning funnel's headline, or null when the deduplication step is not in the release. */
export function funnelHeadline(steps: DataQualityRow[]): string | null {
  const dedupe = step(steps, STEPS.dedupe);
  if (!dedupe) return null;
  return `Of ${count(dedupe.count_in)} stored copies, ${count(dedupe.count_out)} distinct messages remain after removing duplicates.`;
}

/** The header ruling's headline: what is kept and what is never stored, over the fields that have a name. */
export function headerHeadline(fields: HeaderFieldRow[]): string {
  const named = fields.filter((row) => row.field !== OTHER_HEADER_FIELD);
  const usable = named.filter((row) => row.ruling === RULING_USABLE).map((row) => row.field);
  const identifiers = named.filter((row) => row.ruling === RULING_IDENTIFIER).length;
  const content = contentFields(named);
  const parts = [
    usable.length ? `${joinList(usable)} ${usable.length === 1 ? "is" : "are"} kept as metadata` : "none is kept as metadata",
    ...(identifiers
      ? [`${identifiers} identifier field${identifiers === 1 ? " is" : "s are"} replaced by pseudonyms or discarded at ingest`]
      : []),
    ...(content.length ? [`${joinList(content)} ${content.length === 1 ? "is" : "are"} content and never stored`] : []),
  ];
  return `Of ${named.length} named header fields, ${parts.join("; ")}.`;
}

/** Fields ruled identifier that the parser drops instead of retaining (vocab.IDENTIFIERS_NOT_RETAINED). */
const IDENTIFIERS_NOT_RETAINED: readonly string[] = ["X-Origin", "X-FileName"];

/** What the ruling table cannot show by itself: identifiers that are not retained, and the fold that is not a field. */
export function headerNotes(fields: HeaderFieldRow[]): string[] {
  const dropped = fields.filter((row) => IDENTIFIERS_NOT_RETAINED.includes(row.field)).map((row) => row.field);
  return [
    ...(dropped.length
      ? [`${joinList(dropped)} ${dropped.length === 1 ? "is a direct identifier that is" : "are direct identifiers that are"} not retained: the parser drops ${dropped.length === 1 ? "it" : "them"}.`]
      : []),
    ...(fields.some((row) => row.field === OTHER_HEADER_FIELD)
      ? [`${OTHER_HEADER_FIELD} counts occurrences of names without a ruling; it is not a field.`]
      : []),
  ];
}
