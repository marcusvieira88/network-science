# AGENTS.md

Rules for every agent writing code in this repository. Project principles are in
`.specify/memory/constitution.md`; the current work is in `specs/*/tasks.md`. If a rule here
conflicts with the constitution, the constitution wins.

## Before you write

- Read your task, its contract in `specs/*/contracts/`, and the code you are about to touch.
- Search for an existing function before writing a new one. Reuse or extend it; do not copy it.
- Stay inside the paths your task owns. If you need a change elsewhere, ask the lead.

## Privacy rules (non-negotiable)

- Never decode, parse, hold, store or log message content: bodies, subjects, attachments,
  folder names. `Subject` lines are discarded as the header is scanned; body bytes pass through
  the decompressor and are skipped; a folder name is reduced at once to one of four classes
  and never kept.
- Addresses and names exist only in ingest-side packages. Downstream code sees pseudonyms only.
  One documented exception: `risk/aux_public.py` reads the raw archive as the attacker would,
  and `risk/score.py` reads the ingest zone to score guesses; both emit counts only.
- Never log a header value, an address, a name, a pseudonym or the key. Log counts (and
  `file_id` inside the ingest zone).
- Never commit anything from `data/`, a key, or a real address or name.

## Clean code

- Write the simplest code that meets the task. No speculative options, layers or abstractions.
- One function, one job. Keep functions short and names descriptive; avoid abbreviations.
- No duplication: a rule, constant, schema or parameter lives in exactly one place
  (`config.py`, `contracts/schemas.py`) and is imported everywhere else.
- Prefer pure functions: data in, data out. Keep file and network access at the edges.
- Type everything. `mypy --strict` checks `src/` and `tests/`; ruff's annotation rules are on.
  - No `Any` in a function signature. Type untyped input (JSON, config strings) as `object` and
    narrow it with `isinstance`, a typed accessor or a `TypedDict`.
  - No `# type: ignore` without an error code and a reason on the same line; no `cast()` to hide
    a real mismatch.
  - TypeScript in `ui/` is strict: no `any`, no `@ts-ignore`.
- No magic numbers or strings. A tunable parameter is a `Config` field in `config.py`, echoed
  in the run manifest. The definition of a stated hypothesis (for example its working hours or
  its placebo fraction) is a named constant in its own module, on purpose: changing it would
  change the hypothesis.
- Fail loudly: raise a specific error with the documented exit code. Never swallow an
  exception or return a silent default.
- Be deterministic: seed all randomness from `config.py`, sort before writing, no wall-clock
  time in outputs.
- Comments explain why, not what. Delete dead code and commented-out code.
- Add a dependency only with the lead's agreement.

## Tests

- Write the test first and watch it fail, then implement.
- Test behaviour against known answers (synthetic ground truth, hand-computed cases), not
  against the implementation's own output.
- Cover edge cases named in the spec. Never weaken or delete a test to make it pass.

## Done means

- `make gate` is green: lint, types, tests, privacy canary, import boundary. Check the **exit
  code** (`make gate; echo $?`); never judge it from piped output such as `make gate | tail`,
  which reports the exit code of `tail`. If `ui/` changed, `make ui-gate` is green too.
- Reviewed before hand-off with `/code-quality-review` (typing and these rules),
  `/data-privacy-review` (the content and identifier promises) and `/code-review` (correctness).
- Changes that touch analysis, cleaning or hypotheses are also reviewed with `/data-scientist-review`.
- Output tables validate against their contract.
- Docs and contracts still describe what the code does.
- Commits are small, with the task ID in the message (`T024: parse header records`).
- You reported honestly: what works, what does not, what you did not verify.
