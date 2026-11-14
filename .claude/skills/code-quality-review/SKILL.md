---
name: code-quality-review
description: Review new or changed Python and TypeScript code in this repository against AGENTS.md - strict typing, no duplication, parameters in config.py, tests against known answers, determinism, and a gate whose exit code was actually checked. Use before merging a work package, after a fix round, or when asked for a quality, typing or AGENTS.md review.
argument-hint: "Optional scope: a path, a branch, a commit range, or 'full'"
user-invocable: true
disable-model-invocation: false
---

# Code Quality Review

Check that new or changed code in scope follows `AGENTS.md`. This complements the built-in
`/code-review` (correctness bugs) and `/data-privacy-review` (privacy promises): run all three
before a merge. This is a review: do not change code; report findings.

## Scope

- With an argument: that path, branch diff or commit range.
- Without: the diff against `main`, or the last commit if the branch is `main`.

## 1. Run the gates and check their exit codes

Run each and record the **exit status**, not the tail of the output. A piped command such as
`make gate | tail -1` reports the exit status of `tail`, so a red gate looks green.

```bash
export PATH="$HOME/.local/bin:$PATH"
make gate; echo "gate exit $?"
cd ui && npm run lint && npm run typecheck && npm test; echo "ui exit $?"   # if ui/ changed
```

A non-zero exit is a BLOCKER finding.

## 2. Typing (Python)

- `mypy --strict` covers `src/` **and** `tests/` (configured in `pyproject.toml`); it must pass.
- Ruff's `ANN` rules are on. No function parameter or return is typed `Any`; values from JSON or
  other untyped sources are typed `object` and narrowed with `isinstance`, or read through a
  typed accessor or `TypedDict` (see `contracts/counts.py`, `release/tables.py` `require_*`).
  `dict[str, Any]` is acceptable only for a variable that holds parsed JSON.
- No `# type: ignore` without an error code and a one-line reason on the same line.
- No `cast()` to silence a real mismatch; fix the type instead.
- New public functions have precise return types (not `object` where a concrete type exists).

## 3. Typing (TypeScript, `ui/`)

- `tsc --noEmit` in strict mode passes; no `any`, no `@ts-ignore`, no non-null `!` on data that
  comes from `release.json` (it is validated at runtime in `ui/src/lib/data.ts`).

## 4. AGENTS.md rules

For each changed file, check and report violations with `file:line`:

| Rule | What to look for |
|------|------------------|
| One place per rule, constant, schema, parameter | a literal or helper re-declared that exists in `config.py`, `contracts/vocab.py`, `contracts/schemas.py` or another module (search before accepting a new helper) |
| Parameters in `config.py` | a tunable number or threshold as a module constant instead of a `Config` field. Not a violation: the definition of a stated hypothesis kept as a named constant in its module (for example the working hours in `finding/exploratory.py`), because changing it would change the hypothesis |
| No magic numbers or strings | an unexplained literal in logic |
| Simple, single-purpose functions | a function doing several jobs, or abstraction with one caller |
| Fail loudly | a swallowed exception, a silent default, an error without the documented exit code |
| Deterministic | float sums over unordered groups without `stable_sum`; randomness not seeded from `Config`; output order depending on hash or thread order |
| Comments explain why | commented-out code, comments restating the code |
| Owned paths | a change outside the paths the task owns |

## 5. Tests

- New behaviour has a test against a **known answer** (hand-computed case or synthetic ground
  truth), not against the implementation's own output.
- Edge cases named in the spec or the code's docstring are tested.
- No test was weakened, deleted or marked expected-to-fail to make the gate pass. If an expected
  value changed, the reason is in the commit message.
- Statistical tests: check the test data can actually reach the threshold (sample size versus
  the correction used) and that the test data has no artifact of its own (calendar, ordering).

## 6. Docs still match

Contracts in `specs/`, `docs/metrics.md`, `docs/hypotheses*.md` and the README still describe what
the code does after the change.

## Report

1. **Verdict**: `PASS`, `PASS WITH FINDINGS`, or `BLOCKED` (gate red, or a typing rule broken in
   new code).
2. **Gate results** with their exit codes.
3. **Findings**, most severe first: severity, `file:line`, rule, what is wrong, suggested fix.
4. **Not checked**, and why.
