// The Content-Security-Policy rules check-build.mjs enforces on the production build. Presence of
// the directives is not enough: a policy that also allowed eval, inline script, blob: workers or
// another origin would still contain them.

const REQUIRED = ["default-src 'self'", "connect-src 'self'", "script-src 'self'", "font-src 'self'", "object-src 'none'"];

// Directives that load or run code or reach the network: only these sources are allowed.
const CODE_AND_NETWORK = ["default-src", "script-src", "script-src-elem", "script-src-attr", "worker-src", "child-src", "frame-src", "connect-src"];
const CODE_AND_NETWORK_SOURCES = ["'self'", "'none'"];

// A source naming another origin: a URL, a host, a wildcard or a network scheme.
const OTHER_ORIGIN = /:\/\/|\*|^(?:https?|wss?|ftp):$|^[a-z0-9-]+(?:\.[a-z0-9-]+)+(?::\d+)?$/i;

/** [directive name, its sources] in policy order; a repeated name appears more than once. */
export function parsePolicy(policy) {
  const directives = [];
  for (const part of policy.split(";")) {
    const [name, ...sources] = part.trim().split(/\s+/).filter(Boolean);
    if (name) directives.push([name.toLowerCase(), sources]);
  }
  return directives;
}

/** Every reason the policy is not strict enough; empty when it holds. */
export function cspProblems(policy) {
  const problems = [];
  const normalised = policy.replace(/\s+/g, " ");
  for (const directive of REQUIRED) {
    if (!normalised.includes(directive)) problems.push(`lacks "${directive}"`);
  }
  const seen = new Set();
  for (const [name, sources] of parsePolicy(policy)) {
    // A browser applies only the first occurrence, so a later strict copy would hide a weak one.
    if (seen.has(name)) problems.push(`repeats ${name}`);
    seen.add(name);
    for (const source of sources) {
      if (OTHER_ORIGIN.test(source)) problems.push(`${name} allows another origin: ${source}`);
      else if (CODE_AND_NETWORK.includes(name) && !CODE_AND_NETWORK_SOURCES.includes(source)) {
        problems.push(`${name} allows ${source}`);
      }
    }
  }
  return problems;
}
