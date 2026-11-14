// The Content-Security-Policy rules check-build.mjs enforces on the built index.html. Each
// directive must allow exactly these sources, so adding 'unsafe-eval', 'unsafe-inline' or another
// origin to one fails the UI gate. style-src keeps 'unsafe-inline' for the inline style
// attributes React and Recharts set; it cannot run script.
const REQUIRED_DIRECTIVES = {
  "default-src": ["'self'"],
  "script-src": ["'self'"],
  "style-src": ["'self'", "'unsafe-inline'"],
  "img-src": ["'self'", "data:"],
  "font-src": ["'self'", "data:"],
  "connect-src": ["'self'"],
  "object-src": ["'none'"],
  "base-uri": ["'self'"],
  "form-action": ["'none'"],
};

function directives(policy) {
  const parsed = new Map();
  for (const part of policy.split(";")) {
    const [name, ...sources] = part.trim().split(/\s+/);
    if (name) parsed.set(name.toLowerCase(), sources);
  }
  return parsed;
}

/** Problems with `policy`, one string per directive that is missing or allows other sources. */
export function cspProblems(policy) {
  const parsed = directives(policy);
  const problems = [];
  for (const [name, expected] of Object.entries(REQUIRED_DIRECTIVES)) {
    const actual = parsed.get(name);
    if (!actual) {
      problems.push(`Content-Security-Policy lacks "${name}"`);
    } else if ([...actual].sort().join(" ") !== [...expected].sort().join(" ")) {
      problems.push(`Content-Security-Policy "${name}" is "${actual.join(" ")}", expected "${expected.join(" ")}"`);
    }
  }
  return problems;
}
