import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { type ReleaseData, parseRelease } from "@/lib/data";

// Vitest runs from ui/ (jsdom gives import.meta.url a non-file scheme).
const SAMPLE_PATH = resolve(process.cwd(), "public/data/release.sample.json");

/** The committed sample as raw JSON (a fresh copy each call, safe to mutate). */
export function rawSample(): Record<string, unknown> {
  return JSON.parse(readFileSync(SAMPLE_PATH, "utf8")) as Record<string, unknown>;
}

export function sampleData(): ReleaseData {
  return parseRelease(rawSample());
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

export function htmlResponse(status = 200): Response {
  return new Response("<!doctype html><html></html>", { status, headers: { "content-type": "text/html" } });
}
