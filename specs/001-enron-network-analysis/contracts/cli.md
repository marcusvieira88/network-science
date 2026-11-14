# Contract: Command Interface (v1)

The reviewer-facing interface is `make`. The `enron-case` CLI underneath exists so that stages can
be run and tested one at a time.

## Make targets

| Target | Does | Needs corpus | Needs key |
|--------|------|--------------|-----------|
| `make` = `make all` | the one command, below: every step, then serves the explorer at http://localhost:4173 until Ctrl+C | downloads it | creates one if none is configured |
| `make check` | the same steps as `make all` except serving the explorer (CI, reviewers without a server) | downloads it | creates one if none is configured |
| `make sample` | full pipeline on the bundled synthetic corpus, into `data/sample/` and `release-sample/` | no | uses the fixed test key |
| `make gate` | ruff, mypy, pytest (unit, contract, privacy, integration on sample) | no | test key |
| `make key` | create a 32-byte key at `~/.config/enron-case/key` (mode 600) if none exists | no | — |
| `make clean` | remove `data/` work zones, logs and regenerated sample files | no | no |
| `make ui` | export `release/` to `ui/public/data/release.json`, build and serve the explorer (needs Node 20+) | no | no |
| `make ui-sample` | same, from `release-sample/` | no | no |
| `make ui-gate` | UI lint, type check, unit tests, the UI privacy tests, build and build check | no | no |

UI dependencies are installed with `npm ci` only when `ui/package-lock.json` is newer than the
installed tree, so every UI target reuses them.

### The one command

`make` (the default goal, identical to `make all`) runs `scripts/run-all.sh`. It needs no options.
Each step prints one line (`==> step ... ok (Ns)`); its full output goes to
`data/logs/<step>.log` and is shown (last 40 lines) only if the step fails. The first failing step
stops the run: `scripts/run-all.sh` exits with that step's exit code (table below), which `make`
prints (`make: *** [all] Error 3`) before exiting with its own code 2.

1. **Prerequisites**: `uv`, Python 3.12 (as `uv python find 3.12` sees it), Node ≥ 20, `npm`. A
   missing one stops the run with exit code 1 and a one-line message naming it. `make all` also
   needs port 4173 free (checked here, so a busy port fails at once; `UI_PORT=<port> make` uses
   another).
2. **Dependencies**: `uv sync --locked`; `npm ci` in `ui/` (skipped when already installed from
   the current lockfile).
3. **Key**: if no key is configured (no `ENRON_CASE_KEY`, no `ENRON_CASE_KEY_FILE`, no
   `~/.config/enron-case/key`), one is created at `~/.config/enron-case/key` (mode 600, outside the
   repository) and the run says so and where. The key is never printed. A configured key that is
   unusable (wrong length, missing named file, inside the repository) is never replaced: the run
   stops with exit code 3. `KEY_FILE=/other/path make` creates and uses another path.
4. **Corpus**: `enron-case stage fetch`; the download is skipped if the archive is on disk, but
   its SHA-256 is always verified (exit 4 on mismatch).
5. **Pipeline**: `enron-case run` on the real corpus.
6. **Gates**: `make gate` (lint, strict types, all tests, privacy canary) and `make ui-gate`.
7. **Explorer**: `enron-case stage ui-data` exports the release; `npm run build` builds the UI.
8. **Summary**: where the report is (`release/report.md`), how many hypotheses the release holds
   true (`enron-case summary`, read from `release/hypotheses.csv` and `release/exploratory.csv`),
   that every gate passed, and the explorer URL. `make all` then serves the explorer at
   http://localhost:4173 in the foreground until Ctrl+C; `make check` exits 0 instead.

A second `make` reuses the downloaded archive, the key and installed dependencies; it reruns the
pipeline and the gates. On a fresh clone the whole run took about 24 minutes, 20 of them the
download on that connection; the pipeline step takes about 2.5 minutes.

## CLI

```text
enron-case run [--sample] [--from STAGE] [--to STAGE] [--keep-ingest] [--set NAME=VALUE ...]
enron-case stage STAGE [--sample] [--keep-ingest] [--set NAME=VALUE ...]
enron-case verify            # double-run determinism check on the sample
enron-case check-key         # exit 0 if a usable key is configured, else 3
enron-case summary [--sample]  # one line: how many hypotheses the release holds true
enron-case review-merges     # a person judges a seeded sample of identity merges in the terminal;
                             # only counts are kept (counts zone and checks/identity_manual.json)
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

The run aborts if the key is missing, shorter than 32 bytes, resolves to a path inside the
repository, or (key file) grants any permission to group or others (anything but mode 600 or 400). The key is never printed; the manifest records only a key *fingerprint for
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

- Progress goes to stderr as one line per stage with counts and duration. The seconds per stage
  are also written to `data/logs/stage_timings.json` (`data/sample/logs/` for
  `--sample`), git-ignored; `release/run_manifest.json` holds no durations, so identical runs
  write identical bytes.
- Logs never contain header values. Modules outside the ingest zone have no access to them;
  modules inside it log counts and `file_id` only.
- On success the last line on stdout is the path to `release/report.md`.
