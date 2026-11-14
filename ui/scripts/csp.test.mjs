import { describe, expect, it } from "vitest";
import { cspProblems } from "./csp.mjs";

// Known answer: the policy vite.config.ts injects today (check-build.mjs checks the real build;
// importing vite.config here would load esbuild into jsdom).
const CONTENT_SECURITY_POLICY =
  "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; " +
  "font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'none'";

describe("cspProblems", () => {
  it("accepts the policy the build injects today", () => {
    expect(cspProblems(CONTENT_SECURITY_POLICY)).toEqual([]);
  });

  it("rejects a missing policy", () => {
    expect(cspProblems("")).not.toEqual([]);
  });

  it.each([
    ["script-src 'self' 'unsafe-eval'", "script-src"],
    ["script-src 'self' 'unsafe-inline'", "script-src"],
    ["script-src 'self' https://cdn.example", "script-src"],
    ["connect-src 'self' https://collector.example", "connect-src"],
    ["default-src *", "default-src"],
    ["object-src 'self'", "object-src"],
    ["img-src 'self' data: https:", "img-src"],
  ])("rejects a policy that weakens a directive: %s", (directive, name) => {
    const policy = CONTENT_SECURITY_POLICY.replace(new RegExp(`${name} [^;]*`), directive);
    expect(cspProblems(policy).join(" ")).toContain(name);
  });

  it("rejects a policy that drops a required directive", () => {
    const policy = CONTENT_SECURITY_POLICY.replace(/base-uri [^;]*;?/, "");
    expect(cspProblems(policy).join(" ")).toContain("base-uri");
  });
});
