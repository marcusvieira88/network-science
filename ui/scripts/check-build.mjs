#!/usr/bin/env node
// Fails unless the production build in dist/ is self-contained: no URL to another origin that
// the app could request, a Content-Security-Policy that blocks other origins, and every asset
// referenced by index.html present locally. Run after `npm run build`.
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const DIST = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const TEXT_EXTENSIONS = [".html", ".js", ".mjs", ".css", ".json", ".svg", ".txt", ".webmanifest"];
const URL_PATTERN = /\b(?:https?|wss?|ftp):\/\/[^\s"'`<>)\\]+/g;
const PROTOCOL_RELATIVE = /(?:src|href|url\()\s*=?\s*["']?\/\/[^\s"'`<>)]+/g;

// Strings bundled libraries contain that are identifiers or error text, never fetched.
const NON_REQUEST_URLS = [
  { prefix: "http://www.w3.org/", reason: "XML namespace identifier" },
  { prefix: "https://reactjs.org/docs/error-decoder.html", reason: "React error message text" },
  { prefix: "http://fb.me/use-check-prop-types", reason: "React warning message text" },
];

const REQUIRED_CSP = ["default-src 'self'", "connect-src 'self'", "script-src 'self'", "font-src 'self'"];

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}

function isText(path) {
  return TEXT_EXTENSIONS.some((ext) => path.endsWith(ext));
}

const problems = [];
if (!existsSync(join(DIST, "index.html"))) {
  console.error("check-build: dist/index.html not found; run `npm run build` first");
  process.exit(1);
}

for (const path of files(DIST).filter(isText)) {
  const text = readFileSync(path, "utf8");
  const name = relative(DIST, path);
  for (const url of text.match(URL_PATTERN) ?? []) {
    if (!NON_REQUEST_URLS.some((allowed) => url.startsWith(allowed.prefix))) {
      problems.push(`${name}: external URL ${url}`);
    }
  }
  for (const match of text.match(PROTOCOL_RELATIVE) ?? []) {
    problems.push(`${name}: protocol-relative reference ${match}`);
  }
}

const html = readFileSync(join(DIST, "index.html"), "utf8");
const csp = (html.match(/http-equiv="Content-Security-Policy"\s+content="([^"]+)"/)?.[1] ?? "").replaceAll("&#39;", "'");
for (const directive of REQUIRED_CSP) {
  if (!csp.includes(directive)) problems.push(`index.html: Content-Security-Policy lacks "${directive}"`);
}
for (const [, ref] of html.matchAll(/(?:src|href)="([^"]+)"/g)) {
  if (!existsSync(join(DIST, ref.replace(/^\.\//, "")))) problems.push(`index.html: missing local asset ${ref}`);
}

if (problems.length) {
  console.error(`check-build: ${problems.length} problem(s)`);
  for (const problem of problems) console.error(`  ${problem}`);
  process.exit(1);
}
console.log(`check-build: ok (${files(DIST).length} files, no external URLs, CSP present)`);
