import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const CSS = readFileSync(join(import.meta.dirname, "index.css"), "utf8");
const PRINT_START = CSS.indexOf("@media print");
const HSL_DECLARATION = /^\s*(--[\w-]+):\s*\d+ \d+% \d+%;/gm;

function hslTokens(css: string): string[] {
  return [...css.matchAll(HSL_DECLARATION)].map(([, name]) => name ?? "").sort();
}

describe("print theme", () => {
  it("redefines every colour token of the dark theme, so nothing prints dark on white paper", () => {
    expect(PRINT_START).toBeGreaterThan(0);
    const screen = hslTokens(CSS.slice(0, PRINT_START));
    const print = hslTokens(CSS.slice(PRINT_START));
    expect(screen).toContain("--secondary");
    expect(print).toEqual(screen);
  });
});
