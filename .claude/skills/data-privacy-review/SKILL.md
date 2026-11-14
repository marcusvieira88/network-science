---
name: data-privacy-review
description: Review the repository for broken data-privacy promises, above all the promise that message content (bodies, subjects, attachments) is never read, stored or logged. Use when asked for a privacy review, a data-privacy review, or to check that we are not reading employees' messages; also before merging a work package and before submission.
argument-hint: "Optional scope: a path, a branch, a work package (e.g. WP-A), or 'full'"
user-invocable: true
disable-model-invocation: false
---

# Data Privacy Review

Check whether the code, the data on disk and the documentation keep the privacy promises this
project makes. The first and most important promise is: **we never read the content of people's
messages.** A finding against that promise blocks a merge regardless of anything else.

This is a review. Do not change code, data or documents. Report findings; fix only if the user
asks afterwards.

## Scope

- With an argument: review that path, branch diff or work package.
- Without: review the diff against `main` if there is one, otherwise the whole repository.
- If no source code exists yet, review the design documents under `specs/` for promises the
  design cannot keep, and say that code checks were not possible.

## Rules for the reviewer itself

You are bound by the same promise you are checking.

- Never open, print or quote a raw message, the corpus archive, or anything in `data/raw` or
  `data/ingest`. Do not `cat`, `head`, `less`, `tar -x` or read them with any tool.
- When you need evidence from data files, use counts, column names, schemas and yes/no pattern
  matches only (`grep -c`, `grep -l`, a schema dump). Never show matched lines from data.
- In `data/restricted`, `release/` and `checks/`, you may read rows, since they must hold no content or
  identifier. If you find one, report its location and kind, not its value.
- Do not copy an email address, a person's name or a key into your report.

## The promises

Read these first; they define the promises and take precedence over this list where they differ:
`.specify/memory/constitution.md` (Principles I and II), and under the active feature directory
in `specs/`: `contracts/header-allowlist.md`, `contracts/data-contracts.md`, `contracts/cli.md`.

| # | Promise | Severity if broken |
|---|---------|--------------------|
| P1 | Message bodies and attachments are never parsed, held, stored or logged | BLOCKER |
| P2 | `Subject` and other free-text or content-like headers (folder names, file names) are never retained | BLOCKER |
| P3 | Header fields pass only through the documented allowlist; anything else is dropped | BLOCKER |
| P4 | Direct identifiers (addresses, display names, mailbox owners) exist only in the ingest zone | BLOCKER |
| P5 | No table linking pseudonyms to identities exists past the boundary; the ingest zone is purged | HIGH |
| P6 | The key is outside the repository and never in code, logs, artifacts or git history | BLOCKER |
| P7 | Logs and error messages carry counts and pseudonyms only, never header values | HIGH |
| P8 | Published tables respect the minimum group size and contain no pseudonym or identifier | HIGH |
| P9 | Raw data, ingest data and keys are never committed | BLOCKER |
| P10 | The documentation does not claim more than the code does | MEDIUM |

## Checks

Work through every group. For each check record pass, fail or not applicable, with the evidence.

### A. Does any code path reach content? (P1, P2)

1. List every place that opens the corpus archive or a message: search for `tarfile`, `open(`,
   `extractall`, `extract(`, `email.`, `message_from`, `get_payload`, `.read()`, `mailbox`.
2. For each, trace what happens after the header block. The only acceptable behaviour is to stop
   at the first blank line and skip the rest unread. Flag: whole-message reads, standard email
   parsers that load the payload, extraction to disk, reading "a few lines" of the body, size or
   hash of the body, language or encoding detection on the body.
3. Search for content-derived features under any name: `subject`, `body`, `payload`, `text`,
   `snippet`, `preview`, `attachment`, `is_reply`, `is_forward`, `thread`, `keyword`, `topic`,
   `sentiment`, `embedding`, `tokens`, `word`. A reply flag or a hash made from the subject is
   content.
4. Check the attacker-side parser in `risk/` to the same standard; it is not exempt.
5. Check tests and fixtures: synthetic content is fine; real message text is not.

### B. Is the allowlist real? (P3)

1. Compare the fields the parser retains with `contracts/header-allowlist.md`, field by field.
2. Confirm the default is deny: an unknown header's value is discarded and only its name counted.
3. Confirm dropped values are not kept in a variable, exception message, debug dump or cache.
4. Confirm any header field found in the data but missing from the contract has been ruled on.

### C. Do identifiers stay behind the boundary? (P4, P5)

1. Imports: packages after the boundary (`network`, `finding`, `risk`, `release`, `report`, `uiexport`) must
   not import the ingest-side packages. Confirm the import-boundary test exists and passes.
2. File access: every read and write goes through the zone guard; no hard-coded path into
   `data/ingest` or `data/raw` from a downstream package, apart from the documented exceptions.
3. Schemas: no column in a restricted or release table can hold an address, name, owner or raw
   folder. Compare actual columns with `contracts/data-contracts.md`; flag any extra column.
4. If data exists: in `data/restricted`, `release/`, `checks/` (committed counts of the manual
   merge check) and the run manifest, count matches of `@`, and of address- or name-shaped
   strings. Any non-zero count is a finding.
5. No pseudonym-to-identity mapping is written anywhere; the ingest zone does not exist after a
   normal run; `--keep-ingest` is not used by `make` (`scripts/run-all.sh`) or CI.

### D. Key handling (P6)

1. The key comes only from the environment or a file outside the repository; the run refuses a
   missing, short or in-repository key.
2. Search code, tests, CI config and docs for hard-coded secrets. The fixed test key is allowed
   only for the synthetic sample and must be labelled as such.
3. The key is never logged, printed, written to the manifest or passed on a command line.
4. Search git history for key files and key-shaped strings.

### E. Logs and errors (P7)

1. Read every logging and print call and every exception message in ingest-side packages: none
   may interpolate a header value, address, name or path containing an owner name.
2. Check that tracebacks cannot carry header values (no header text in exception arguments).
3. Check progress output, the run manifest and CI logs for the same.

### F. Release (P8)

1. Every file written under `release/` passes through the single minimum-group-size check.
2. No pseudonym, organization pseudonym or identifier pattern in any release file.
3. No per-person row, and no cell describing a group below the minimum, including derived rows
   (a total minus a published part can reveal a suppressed group).
4. Charts, slides and the report use only release tables.

### G. Repository hygiene (P9)

1. `.gitignore` covers `data/`, key files and sample outputs; `git status` shows none of them.
2. Search git history, not just the working tree, for data files, archives and large blobs.
3. No real address or name in source, tests, docs, commit messages or CI configuration, except
   where a document explicitly and deliberately names a public fact.

### H. Honesty of the claims (P10)

1. Compare each privacy statement in `README.md`, `docs/` and the report with what the code
   does. Flag claims that are stronger than the implementation ("anonymous" for pseudonymized
   data, "content is never downloaded" when the archive on disk contains it).
2. Confirm the known limits are stated: body bytes pass through the decompressor; pseudonymized
   data is still personal data; whoever holds the key can test candidates.

### I. Run the automated privacy tests, if they exist

Run the privacy test suite (canary, import boundary, zone guard, key handling) and the
group-size tests on the synthetic sample. Report results. A missing or skipped canary test is
itself a HIGH finding: the promise is then unverified.

## Report

Output in this order:

1. **Verdict**: one line — `PASS`, `PASS WITH FINDINGS`, or `BLOCKED` (any BLOCKER open).
2. **Content promise**: one short paragraph answering directly: does anything in scope read,
   keep or log message content? Say what you checked and what you could not check.
3. **Findings table**, most severe first:

   | ID | Severity | Promise | Location (`file:line`) | What breaks the promise | Suggested fix |
   |----|----------|---------|------------------------|-------------------------|---------------|

4. **Checks performed**: groups A–I with pass / fail / not applicable / not checked.
5. **Not verified**: anything you could not check and why (no code yet, no data on disk, tests
   absent).

Be exact about certainty: separate what you confirmed by reading code or running a test from
what you infer. Do not report a promise as kept if you only failed to find a violation in a
partial search; say how far the search went.

If the project keeps a workflow log (`docs/ai-workflow-log.md`), offer to append a one-line
summary of the review; do not write to it unasked.
