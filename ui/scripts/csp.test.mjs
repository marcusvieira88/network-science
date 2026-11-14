import { describe, expect, it } from "vitest";

import { cspProblems } from "./csp.mjs";

// A strict policy of the shape the build ships; check-build.mjs checks the real one in dist/.
const STRICT =
  "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; " +
  "font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'none'";

describe("Content-Security-Policy check", () => {
  it("accepts a strict policy", () => {
    expect(cspProblems(STRICT)).toEqual([]);
  });

  it.each([
    ["eval", "script-src 'self' 'unsafe-eval'"],
    ["inline script", "script-src 'self' 'unsafe-inline'"],
    ["blob: workers", "worker-src 'self' blob:"],
    ["data: scripts", "script-src 'self' data:"],
    ["another origin", "connect-src 'self' https://telemetry.example"],
    ["a bare host", "img-src 'self' cdn.example.com"],
    ["a wildcard", "img-src *"],
    ["any https origin", "font-src 'self' https:"],
  ])("refuses %s", (_label, weakening) => {
    expect(cspProblems(`${STRICT}; ${weakening}`)).not.toEqual([]);
  });

  it("refuses a weak directive hidden before a strict copy", () => {
    expect(cspProblems(`script-src 'self' 'unsafe-eval'; ${STRICT}`)).toContain("repeats script-src");
  });

  it("refuses a policy that lacks a required directive", () => {
    expect(cspProblems("default-src 'self'; script-src 'self'")).toContain(`lacks "connect-src 'self'"`);
  });
});
