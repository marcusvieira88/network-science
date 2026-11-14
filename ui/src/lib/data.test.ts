import { describe, expect, it } from "vitest";

import { DataError, RELEASE_URL, SAMPLE_URL, TABLE_COLUMNS, loadRelease, parseRelease } from "@/lib/data";
import { PrivacyError } from "@/lib/privacy";
import { htmlResponse, jsonResponse, rawSample } from "@/test/sample";

type Tables = Record<string, Record<string, unknown>[]>;

function tablesOf(doc: Record<string, unknown>): Tables {
  return doc.tables as Tables;
}

function firstRow(doc: Record<string, unknown>, table: string): Record<string, unknown> {
  const row = tablesOf(doc)[table]?.[0];
  if (!row) throw new Error(`fixture has no ${table} rows`);
  return row;
}

describe("parseRelease", () => {
  it("accepts the committed sample with every release table", () => {
    const data = parseRelease(rawSample());
    expect(Object.keys(data.tables).sort()).toEqual(Object.keys(TABLE_COLUMNS).sort());
    expect(data.tables.hypotheses.map((h) => h.hypothesis)).toEqual(["H1", "H2", "H3", "H4"]);
    expect(data.tables.data_quality[1]).toMatchObject({ step: "deduplicate", count_in: 6731, count_out: 2721 });
    expect(data.events).toHaveLength(5);
    expect(data.run.seed).toBe(20011202);
  });

  it("reads the exploratory crisis and reference windows", () => {
    const data = parseRelease(rawSample());
    expect(data.windows).toEqual({
      crisis: { start: "2001-08-14", end: "2001-12-02" },
      reference: { start: "2000-08-14", end: "2000-12-02" },
    });
  });

  it("rejects a missing or malformed window", () => {
    const missing = rawSample();
    delete missing.windows;
    expect(() => parseRelease(missing)).toThrow(/windows/);
    const reversed = rawSample();
    reversed.windows = {
      crisis: { start: "2001-12-02", end: "2001-08-14" },
      reference: { start: "2000-08-14", end: "2000-12-02" },
    };
    expect(() => parseRelease(reversed)).toThrow(/window crisis/);
  });

  it("keeps suppressed cells as null", () => {
    const data = parseRelease(rawSample());
    const tenPlus = data.tables.degree_distribution.filter((row) => row.degree_bucket === "10+");
    expect(tenPlus.length).toBeGreaterThan(0);
    expect(tenPlus.every((row) => row.persons === null)).toBe(true);
  });

  it("accepts null for a float the release could not compute (NaN or ±inf upstream)", () => {
    const doc = rawSample();
    Object.assign(firstRow(doc, "hypotheses"), { effect: null, ci_low: null, ci_high: null, null_z: null });
    firstRow(doc, "artifact_checks").passes = null;
    const data = parseRelease(doc);
    expect(data.tables.hypotheses[0]?.effect).toBeNull();
    expect(data.tables.artifact_checks[0]?.passes).toBeNull();
  });

  it("reads the exploratory family E1–E20 with nullable equalised results", () => {
    const data = parseRelease(rawSample());
    const rows = data.tables.exploratory;
    expect(rows.map((r) => r.hypothesis)).toEqual(Array.from({ length: 20 }, (_, i) => `E${i + 1}`));
    expect(rows.filter((r) => r.outcome === "confident").map((r) => r.hypothesis)).toEqual(["E12"]);
    expect(rows[0]?.equalised_median).toBeNull();
    expect(rows[11]).toMatchObject({ family: "second", equalised_median: 0.1 });
  });

  it("rejects an exploratory outcome outside its enum", () => {
    const doc = rawSample();
    firstRow(doc, "exploratory").outcome = "supported";
    expect(() => parseRelease(doc)).toThrow(/column outcome/);
  });

  it("rejects a missing table", () => {
    const doc = rawSample();
    delete tablesOf(doc).risk;
    expect(() => parseRelease(doc)).toThrow(/missing tables: risk/);
  });

  it("rejects a wrong value type", () => {
    const doc = rawSample();
    firstRow(doc, "community_groups").n_persons = "14";
    expect(() => parseRelease(doc)).toThrow(DataError);
  });

  it("rejects a value outside an enum", () => {
    const doc = rawSample();
    firstRow(doc, "hypotheses").supported = "maybe";
    expect(() => parseRelease(doc)).toThrow(/column supported/);
  });

  it("rejects an extra column", () => {
    const doc = rawSample();
    firstRow(doc, "community_groups").members = 3;
    expect(() => parseRelease(doc)).toThrow(DataError);
  });

  it("rejects an unknown format version", () => {
    const doc = rawSample();
    doc.format_version = 2;
    expect(() => parseRelease(doc)).toThrow(/format_version/);
  });

  it("rejects identifier-shaped values and small person counts", () => {
    const leaky = rawSample();
    firstRow(leaky, "header_fields").ruling = "a@b.example";
    expect(() => parseRelease(leaky)).toThrow(PrivacyError);
    const small = rawSample();
    firstRow(small, "community_groups").n_persons = 4;
    expect(() => parseRelease(small)).toThrow(PrivacyError);
  });
});

describe("loadRelease", () => {
  it("loads release.json when it exists", async () => {
    const urls: string[] = [];
    const result = await loadRelease(async (url) => {
      urls.push(url);
      return jsonResponse(rawSample());
    }, "/");
    expect(result).toMatchObject({ status: "ok", source: "release" });
    expect(urls).toEqual([`/${RELEASE_URL}`]);
  });

  it("falls back to the sample only when release.json is missing", async () => {
    for (const missing of [new Response("", { status: 404 }), htmlResponse()]) {
      const result = await loadRelease(
        async (url) => (url.endsWith(RELEASE_URL) ? missing.clone() : jsonResponse(rawSample())),
        "/",
      );
      expect(result).toMatchObject({ status: "ok", source: "sample" });
    }
  });

  it("reports a malformed release.json instead of falling back", async () => {
    const result = await loadRelease(async (url) =>
      url.endsWith(RELEASE_URL) ? new Response("{not json", { headers: { "content-type": "application/json" } }) : jsonResponse(rawSample()),
    "/");
    expect(result).toEqual({ status: "error", message: "release.json is not valid JSON" });
  });

  it("reports when neither file exists", async () => {
    const result = await loadRelease(async () => new Response("", { status: 404 }), "/");
    expect(result.status).toBe("error");
  });

  it("requests only the two local data files", async () => {
    const urls: string[] = [];
    await loadRelease(async (url) => {
      urls.push(url);
      return new Response("", { status: 404 });
    }, "./");
    expect(urls).toEqual([`./${RELEASE_URL}`, `./${SAMPLE_URL}`]);
  });
});
