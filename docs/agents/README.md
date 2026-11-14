# Agent protocol

> **The parallel phase is over.** This protocol and the briefs `WP-A.md`…`WP-J.md` are the
> record of how the ten work packages were built at the same time against a frozen foundation;
> all ten were merged. Later work (artifact checks, the review fix rounds, the config refactor,
> hypotheses H5–H25, the retention check, the record profile, attacker A3, the one command, the
> extra UI views) was done one change at a time on
> short-lived branches (`fix/…`, `refactor/…`, `ui/…`, `docs/…`, `skill/…`): the lead or a single
> implementation agent made the change, the review skills (`/code-review`,
> `/data-privacy-review`, `/code-quality-review`, and `/data-scientist-review` for analysis
> changes) checked it, and the lead merged it. The foundation is no longer frozen: `AGENTS.md`
> and the contracts' change rule govern. The current design is in `docs/architecture.md`; what
> happened, in order, is in `docs/ai-workflow-log.md`.

You are one of several agents building this repository in parallel. Each agent owns one work
package (WP) and works in its own git worktree. Read, in order:

1. `AGENTS.md` (coding rules) and `.specify/memory/constitution.md` (principles I and II are
   non-negotiable).
2. Your brief: `docs/agents/WP-<X>.md`.
3. Your tasks in `specs/001-enron-network-analysis/tasks.md` (search for `(WP-<X>)`).
4. The contracts you read and write: `specs/001-enron-network-analysis/contracts/` and their
   code form in `src/enron_case/contracts/` (`schemas.py`, `vocab.py`, `counts.py`).

## The foundation you build on (do not modify)

| Module | Use it for |
|--------|------------|
| `enron_case.context.StageContext` | all I/O: `ctx.read(table)`, `ctx.write(table, df)`, `ctx.write_counts(name, dict)`, `ctx.read_counts(name)`, `ctx.path(zone, name, mode)`, `ctx.archive`, `ctx.has_truth()`, `ctx.read_truth()`, `ctx.config`, `ctx.log(msg)` |
| `enron_case.contracts.schemas` | table contracts; `ctx.write` conforms, validates, leak-checks and fingerprints for you |
| `enron_case.contracts.vocab` | enums, `file_id`, `msg_key`, `folder_class`, `format_pseudonym`, role strengths |
| `enron_case.contracts.counts` | shapes of the counts side outputs |
| `enron_case.config.Config` | every parameter; never hard-code one |
| `enron_case.errors` | raise these; each maps to an exit code |
| `enron_case.zones` | zone guard (you do not call it directly; `ctx` does) |
| `enron_case.synth` | synthetic corpus, ground truth and a reference fixture for every table |

Shared files owned by the lead (ask, do not edit): `pyproject.toml`, `uv.lock`, `Makefile`,
`src/enron_case/{cli,context,config,zones,manifest,errors}.py`, `src/enron_case/contracts/`,
`src/enron_case/synth/`, `tests/conftest.py`, `tests/helpers.py`, `tests/contract/`,
`tests/privacy/`. If you need a new dependency or a contract change, stop and say so in your
final report instead of making it.

## Your stage

Implement `src/enron_case/<package>/stage.py` with the function the orchestrator calls (named in
your brief), taking `ctx: StageContext` and returning `None`. The orchestrator
(`src/enron_case/cli.py`) finds it by name.

## Tests

- Test fixtures: the session fixtures `synth` and `synth_nochange` (see `tests/conftest.py`)
  give you a generated corpus with `synth.table(name)`, `synth.truth()`, `synth.counts(name)`,
  `synth.archive`.
- `helpers.ctx_with_fixtures(package, synth, tmp_path, tables=(...))` gives you a sample-mode
  context whose zones already hold the named fixture tables, the archive, the truth and the
  counts. Run your stage on it and compare with the reference fixture.
- Write tests first. Test against known answers, never against your own output.
- Put tests in `tests/unit/<package>/`.

## Commands

```bash
export PATH="$HOME/.local/bin:$PATH"     # uv lives here
uv sync
make gate                                 # must be green before you finish
uv run pytest tests/unit/<package> -q     # while working
```

## Hard rules

- Never read, store or log message content, or a header value outside the ingest side.
- Never log an address, a name or the key. Log counts.
- Stay inside the paths your brief says you own.
- Do not open `data/raw` or the real corpus. Agents build and test on the synthetic corpus only;
  the lead runs the real corpus.

## Finishing

1. `make gate` green.
2. Commit on a branch named `wp/<x>-<package>` (for example `wp/a-ingest`) with the task IDs in
   each message, ending with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
   Do not push.
3. Final report, in this order: branch name and head commit; tasks done; tasks not done and
   why; anything in the contracts that was unclear or that you needed changed; what you did not
   verify.
