/**
 * The explorer's only data: `release.json`, written by the `ui-data` stage
 * (src/enron_case/uiexport/export.py documents the shape). Column guards below are the single
 * source of both the TypeScript row types and the runtime validation.
 */
import { assertReleasePrivacy } from "@/lib/privacy";

export const FORMAT_VERSION = 2;
export const RELEASE_URL = "data/release.json";
export const SAMPLE_URL = "data/release.sample.json";

type Guard<T> = (value: unknown) => value is T;

const isString: Guard<string> = (v): v is string => typeof v === "string";
const isNumber: Guard<number> = (v): v is number => typeof v === "number" && Number.isFinite(v);
const isInt: Guard<number> = (v): v is number => Number.isInteger(v);
const isBoolean: Guard<boolean> = (v): v is boolean => typeof v === "boolean";
const isIsoDate: Guard<string> = (v): v is string => isString(v) && /^\d{4}-\d{2}-\d{2}$/.test(v);
const oneOf =
  <const T extends readonly string[]>(values: T): Guard<T[number]> =>
  (v): v is T[number] =>
    isString(v) && values.includes(v);
const nullable =
  <T>(guard: Guard<T>): Guard<T | null> =>
  (v): v is T | null =>
    v === null || guard(v);
/** A hypothesis id ends in its number: the one list of hypotheses is ordered by it. */
export const HYPOTHESIS_ID = /(\d+)$/;
const isNumberedId: Guard<string> = (v): v is string => isString(v) && HYPOTHESIS_ID.test(v);
/** A float cell: null where the release table holds NaN or ±inf (not computable). */
const isFloat = nullable(isNumber);

export const METRICS = [
  "volume",
  "active_persons",
  "density",
  "reciprocity",
  "indegree_gini",
  "cross_community_share",
  "external_share",
  "tie_turnover",
] as const;
export const SCOPES = ["core", "observed"] as const;
export const HYPOTHESES = ["H1", "H2", "H3", "H4"] as const;
export const SUPPORT = ["yes", "no", "inconclusive"] as const;
export const CONFIDENCE = ["high", "moderate", "low"] as const;
export const RELEASE_VARIANTS = ["R0", "R1", "R2"] as const;
export const ATTACKERS = ["A1", "A2"] as const;
export const EXPLORATORY_FAMILIES = ["first", "second"] as const;
export const DIRECTIONS = ["up", "down"] as const;
export const EXPLORATORY_OUTCOMES = ["confident", "inconclusive", "not supported"] as const;

export type Metric = (typeof METRICS)[number];
export type Scope = (typeof SCOPES)[number];

const HYPOTHESIS_COLUMNS = {
  hypothesis: oneOf(HYPOTHESES),
  metric: oneOf(METRICS),
  scope: oneOf(SCOPES),
  change_week: nullable(isIsoDate),
  p_perm: isFloat,
  p_holm: isFloat,
  effect: isFloat,
  ci_low: isFloat,
  ci_high: isFloat,
  null_z: isFloat,
  loo_min_effect: isFloat,
  loo_max_effect: isFloat,
  robust_variants_passed: isInt,
  robust_variants_total: isInt,
  supported: oneOf(SUPPORT),
  confidence: oneOf(CONFIDENCE),
  is_headline: isBoolean,
};

/** Release tables and their columns, mirroring src/enron_case/contracts/schemas.py (zone 3). */
export const TABLE_COLUMNS = {
  data_quality: {
    order: isInt,
    step: isString,
    count_in: isInt,
    count_out: isInt,
    removed: isInt,
    rule: nullable(isString),
    precision: nullable(isNumber),
    recall: nullable(isNumber),
  },
  header_fields: { field: isString, occurrences: isInt, ruling: isString },
  weekly_metrics: {
    scope: oneOf(SCOPES),
    week: isIsoDate,
    metric: oneOf(METRICS),
    value: nullable(isNumber),
    n_active: nullable(isInt),
    variant: isString,
  },
  hypotheses: HYPOTHESIS_COLUMNS,
  artifact_checks: {
    hypothesis: oneOf(HYPOTHESES),
    check: isString,
    statistic: isFloat,
    ci_low: isFloat,
    ci_high: isFloat,
    n_units: nullable(isInt),
    passes: nullable(isBoolean),
    note: isString,
  },
  exploratory: {
    order: isInt,
    hypothesis: isNumberedId,
    family: oneOf(EXPLORATORY_FAMILIES),
    measure: isString,
    direction: oneOf(DIRECTIONS),
    custodians: nullable(isInt),
    median_change: isFloat,
    ci_low: isFloat,
    ci_high: isFloat,
    p: isFloat,
    p_holm: isFloat,
    placebo_custodians: nullable(isInt),
    placebo_median: isFloat,
    placebo_ci_low: isFloat,
    placebo_ci_high: isFloat,
    // Null when the comparison covers fewer than k custodians and is suppressed in the release.
    placebo_passes: nullable(isBoolean),
    loo_stable: nullable(isBoolean),
    outcome: nullable(oneOf(EXPLORATORY_OUTCOMES)),
    caveat: isString,
    equalised_median: isFloat,
    equalised_ci_low: isFloat,
    equalised_ci_high: isFloat,
    equalised_p: isFloat,
    // Retention check (contract 1.4): the hypothesis on a measure inbox retention cannot move.
    retention_median: isFloat,
    retention_ci_low: isFloat,
    retention_ci_high: isFloat,
    retention_passes: nullable(isBoolean),
  },
  risk: {
    release_variant: oneOf(RELEASE_VARIANTS),
    attacker: oneOf(ATTACKERS),
    n_targets: isInt,
    unique_share: isFloat,
    median_anonymity_set: isFloat,
    reid_top1: isFloat,
    reid_ci_low: isFloat,
    reid_ci_high: isFloat,
    utility_effect_ratio: isFloat,
    finding_survives: nullable(isBoolean),
  },
  degree_distribution: { period: isString, degree_bucket: isString, persons: nullable(isInt) },
  community_graph: {
    week: isIsoDate,
    src_group: isString,
    dst_group: isString,
    weight: nullable(isNumber),
    n_messages: nullable(isInt),
  },
  community_groups: { group: isString, n_persons: isInt },
} as const;

export type TableName = keyof typeof TABLE_COLUMNS;
export type Row<T extends TableName> = {
  [C in keyof (typeof TABLE_COLUMNS)[T]]: (typeof TABLE_COLUMNS)[T][C] extends Guard<infer V> ? V : never;
};

export type DataQualityRow = Row<"data_quality">;
export type HeaderFieldRow = Row<"header_fields">;
export type WeeklyMetricRow = Row<"weekly_metrics">;
export type HypothesisRow = Row<"hypotheses">;
export type ArtifactCheckRow = Row<"artifact_checks">;
export type ExploratoryRow = Row<"exploratory">;
export type RiskRow = Row<"risk">;
export type DegreeRow = Row<"degree_distribution">;
export type CommunityEdgeRow = Row<"community_graph">;
export type CommunityGroupRow = Row<"community_groups">;

export interface PublicEvent {
  date: string;
  label: string;
}

/** An inclusive date range, ISO dates. */
export interface Period {
  start: string;
  end: string;
}

/** The exploratory windows of docs/hypotheses-exploratory.md (config.CRISIS_WINDOW, REFERENCE_WINDOW). */
export interface Windows {
  crisis: Period;
  reference: Period;
}

export interface RunInfo {
  code_version: string;
  sample: boolean;
  seed: number;
  parameters: Record<string, unknown>;
}

export interface ReleaseData {
  format_version: number;
  contract_version: string;
  run: RunInfo;
  events: PublicEvent[];
  windows: Windows;
  tables: { [T in TableName]: Row<T>[] };
}

export class DataError extends Error {
  override name = "DataError";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, where: string): Record<string, unknown> {
  if (!isRecord(value)) throw new DataError(`${where} is not an object`);
  return value;
}

function requireArray(value: unknown, where: string): unknown[] {
  if (!Array.isArray(value)) throw new DataError(`${where} is not a list`);
  return value;
}

function parseRows<T extends TableName>(name: T, value: unknown): Row<T>[] {
  const columns: Record<string, Guard<unknown>> = TABLE_COLUMNS[name];
  const expected = Object.keys(columns);
  return requireArray(value, `table ${name}`).map((raw, index) => {
    const row = requireRecord(raw, `${name} row ${index}`);
    const keys = Object.keys(row);
    if (keys.length !== expected.length || keys.some((key, i) => key !== expected[i])) {
      throw new DataError(`${name} row ${index} has columns [${keys.join(", ")}]`);
    }
    for (const column of expected) {
      if (!columns[column]?.(row[column])) {
        throw new DataError(`${name} row ${index}: bad value in column ${column}`);
      }
    }
    return row as Row<T>;
  });
}

function parseRun(value: unknown): RunInfo {
  const run = requireRecord(value, "run");
  if (!isString(run.code_version) || !isBoolean(run.sample) || !isInt(run.seed)) {
    throw new DataError("run block is malformed");
  }
  return {
    code_version: run.code_version,
    sample: run.sample,
    seed: run.seed,
    parameters: requireRecord(run.parameters, "run.parameters"),
  };
}

function parseEvents(value: unknown): PublicEvent[] {
  return requireArray(value, "events").map((raw, index) => {
    const event = requireRecord(raw, `event ${index}`);
    if (!isIsoDate(event.date) || !isString(event.label)) {
      throw new DataError(`event ${index} is malformed`);
    }
    return { date: event.date, label: event.label };
  });
}

function parsePeriod(value: unknown, name: string): Period {
  const period = requireRecord(value, `window ${name}`);
  if (!isIsoDate(period.start) || !isIsoDate(period.end) || period.end < period.start) {
    throw new DataError(`window ${name} is malformed`);
  }
  return { start: period.start, end: period.end };
}

function parseWindows(value: unknown): Windows {
  const windows = requireRecord(value, "windows");
  return { crisis: parsePeriod(windows.crisis, "crisis"), reference: parsePeriod(windows.reference, "reference") };
}

/** Every group a tie names must be a published group (release/variants.py builds it so). */
function checkGraphGroups(tables: ReleaseData["tables"]): void {
  const published = new Set(tables.community_groups.map((row) => row.group));
  const unknown = tables.community_graph.filter((row) => !published.has(row.src_group) || !published.has(row.dst_group));
  if (unknown.length) throw new DataError(`community_graph has ${unknown.length} ties to unpublished groups`);
}

/** Validate an untrusted JSON value as a release document; throws DataError. */
export function parseRelease(value: unknown): ReleaseData {
  const doc = requireRecord(value, "release data");
  if (doc.format_version !== FORMAT_VERSION) {
    throw new DataError(`unsupported format_version ${String(doc.format_version)}`);
  }
  if (!isString(doc.contract_version)) throw new DataError("contract_version is missing");
  const rawTables = requireRecord(doc.tables, "tables");
  const names = Object.keys(TABLE_COLUMNS) as TableName[];
  const missing = names.filter((name) => !(name in rawTables));
  if (missing.length) throw new DataError(`missing tables: ${missing.join(", ")}`);
  const tables = Object.fromEntries(
    names.map((name) => [name, parseRows(name, rawTables[name])]),
  ) as ReleaseData["tables"];
  checkGraphGroups(tables);
  const data: ReleaseData = {
    format_version: FORMAT_VERSION,
    contract_version: doc.contract_version,
    run: parseRun(doc.run),
    events: parseEvents(doc.events),
    windows: parseWindows(doc.windows),
    tables,
  };
  assertReleasePrivacy(data);
  return data;
}

export type LoadResult =
  | { status: "ok"; data: ReleaseData; source: "release" | "sample" }
  | { status: "error"; message: string };

type FetchLike = (url: string) => Promise<Response>;

/** A file the static server does not have: a 404, or a dev-server HTML fallback page. */
function isMissing(response: Response): boolean {
  const type = response.headers.get("content-type") ?? "";
  return !response.ok || type.includes("text/html");
}

async function readJson(response: Response, label: string): Promise<ReleaseData> {
  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw new DataError(`${label} is not valid JSON`);
  }
  return parseRelease(value);
}

/**
 * Load `release.json`; only if it does not exist, fall back to the bundled sample. A file that
 * exists but is malformed is an error, never silently replaced by the sample.
 */
export async function loadRelease(fetchFn: FetchLike = fetch, base: string = import.meta.env.BASE_URL): Promise<LoadResult> {
  try {
    const release = await fetchFn(`${base}${RELEASE_URL}`);
    if (!isMissing(release)) {
      return { status: "ok", data: await readJson(release, "release.json"), source: "release" };
    }
    const sample = await fetchFn(`${base}${SAMPLE_URL}`);
    if (isMissing(sample)) {
      return { status: "error", message: "No release data found. Run `make ui` or `make ui-sample` first." };
    }
    return { status: "ok", data: await readJson(sample, "release.sample.json"), source: "sample" };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { status: "error", message };
  }
}
