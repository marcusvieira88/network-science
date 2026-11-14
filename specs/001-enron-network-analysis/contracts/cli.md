# Contract: Command Interface (v1)

The reviewer-facing interface is `make`. The `enron-case` CLI underneath exists so that stages can
be run and tested one at a time.

## Make targets

| Target | Does | Needs corpus | Needs key |
|--------|------|--------------|-----------|
| `make all` | install locked deps, fetch + verify corpus, run all stages, run gate, write `release/report.md` | downloads it | yes |
| `make sample` | same pipeline on the bundled synthetic corpus, into `data/sample/` and `release-sample/` | no | uses the fixed test key |
| `make gate` | ruff, mypy, pytest (unit, contract, privacy, integration on sample) | no | test key |
| `make key` | create a 32-byte key at `~/.config/enron-case/key` (mode 600) if none exists | no | — |
| `make clean` | remove `data/` and regenerated release files | no | no |
| `make ui` | export `release/` to `ui/public/data/release.json`, install UI dependencies from the lockfile, build and serve the explorer locally (needs Node 20+; not part of `make all`) | no | no |
| `make ui-sample` | same, from `release-sample/` | no | no |
| `make ui-gate` | UI lint, type check, unit tests and the UI privacy tests | no | no |

`make all` is the one command of the brief. If no key exists it stops with exit code 3 and a
one-line instruction to run `make key`; it never generates a key silently and never writes one
inside the repository.

## CLI

```text
enron-case run [--sample] [--from STAGE] [--to STAGE] [--keep-ingest] [--set NAME=VALUE ...]
enron-case stage STAGE [--sample]
enron-case verify            # double-run determinism check on the sample
```

`STAGE` ∈ `fetch, parse, clean, identity, pseudo, network, finding, risk, release, report, ui-data`.
`ui-data` is not part of `run` unless `--to ui-data` is given.

| Option | Meaning |
|--------|---------|
| `--sample` | use the synthetic corpus and the test key |
| `--from/--to` | run a contiguous range of stages; earlier outputs must exist and match the manifest |
| `--keep-ingest` | do not purge the ingest zone at the end (debugging; prints a warning; never used by `make all`) |
| `--set` | override a parameter from `config.py`; recorded in the run manifest |

## Key resolution

1. `ENRON_CASE_KEY` (hex, 64 chars), else
2. file at `ENRON_CASE_KEY_FILE`, else
3. `~/.config/enron-case/key`.

The run aborts if the key is missing, shorter than 32 bytes, or resolves to a path inside the
repository. The key is never printed; the manifest records only a key *fingerprint for
comparison between runs* computed as HMAC(key, "fingerprint-v1") truncated to 8 hex characters.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | success |
| 2 | usage error |
| 3 | key missing or unsafe |
| 4 | corpus checksum mismatch or download failure |
| 5 | contract violation (a stage produced a table that fails its schema) |
| 6 | privacy violation (zone guard, k-threshold, or canary) |
| 7 | pseudonym collision |

## Output and logging

- Progress goes to stderr as one line per stage with counts and duration.
- Logs never contain header values. Modules outside the ingest zone have no access to them;
  modules inside it log counts and `file_id` only.
- On success the last line on stdout is the path to `release/report.md`.
