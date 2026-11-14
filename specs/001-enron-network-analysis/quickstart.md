# Quickstart: run and validate

How a reviewer (or an agent checking its own work) proves the case works end to end. Interface
details are in [contracts/cli.md](contracts/cli.md); table schemas in
[contracts/data-contracts.md](contracts/data-contracts.md).

## Prerequisites

- Python 3.12 and `uv`
- `make`, about 3 GB free disk, internet access for the corpus download (about 450 MB)

## 1. Validate without the corpus (about 2 minutes)

```bash
make gate      # lint, types, all tests on the synthetic corpus
make sample    # full pipeline on the synthetic corpus
```

Expected:
- `make gate` exits 0.
- `release-sample/report.md` exists and its data-quality section reports dedupe and identity
  precision ≥ 0.95 against the generator's ground truth (SC-004).
- The planted change is reported within one week of its true date (SC-006).

## 2. Run the case (under 30 minutes)

```bash
make key       # once; writes a key outside the repository
make all
```

Expected:
- Exit 0; last line is `release/report.md`.
- `data/ingest/` no longer exists after the run.
- `release/` contains the tables listed in the data contract and `run_manifest.json`.

## 3. Validation scenarios

| # | Check | How | Expected |
|---|-------|-----|----------|
| V1 | Content never enters (SC-001) | `uv run pytest tests/privacy -k canary` | pass; no marker in any zone, log or manifest |
| V2 | Zone boundary | `uv run pytest tests/privacy -k boundary` | pass; no downstream package imports an ingest-side package |
| V3 | Stable pseudonyms (FR-010) | `enron-case verify` | all fingerprints equal across two runs |
| V4 | Key dependence | run sample with a second key, compare `entities_p` | zero pseudonyms in common |
| V5 | No key, no run | `env -u ENRON_CASE_KEY ENRON_CASE_KEY_FILE=/nonexistent make all` | exit 3, nothing written |
| V6 | Minimum group size (SC-008) | `uv run pytest tests/unit/release -k kanon` and inspect `release/*.csv` | no person count below 5 |
| V7 | One finding (SC-005) | open `release/hypotheses.csv` | four rows; at most one `is_headline`; each with effect, interval, p, robustness, confidence |
| V8 | Risk measured (SC-007) | open `release/risk.csv` | rows for R0/R1/R2 × attackers with re-identification rates and utility |
| V9 | No identifiers released | `grep -rE '@|p_[a-z2-7]{16}' release/` | no match |
| V10 | Reproducible from clean clone | fresh clone on another machine, steps 1–2 | same fingerprints given the same key |

## 4. Reading order for a reviewer

1. `release/report.md` — what was found, the finding, the risk, the limits
2. `docs/decision-record.md` — one page
3. `docs/architecture.md` — diagrams of zones, stages, boundary
4. `docs/ai-workflow.md` — how agents were used and checked
5. `docs/slides.md` — the 15-minute walk-through
