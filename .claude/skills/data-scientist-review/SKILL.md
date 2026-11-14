---
name: data-scientist-review
description: Review the analysis in this repository as a data scientist - whether the data flow, the cleaning decisions, the hypotheses and the statistical tests are sound and free of methodological flaws, and whether published claims match the evidence. Use when asked for a data-science review, a methodology or statistics review, an analysis review or a hypothesis review; also before merging a change that touches cleaning, identity resolution, network metrics, hypotheses or the report.
argument-hint: "Optional scope: a path, a branch, a hypothesis family (H, E, artifact checks), a stage, or 'full'"
user-invocable: true
disable-model-invocation: false
---

# Data Scientist Review

Check whether the **analysis** holds up: the data reaching each stage is what the contracts say,
every cleaning rule is justified and its effect measured, the hypotheses were fixed before their
results, the tests fit the data, and every published claim is supported at the standard it
states. Code style is `/code-quality-review`'s job, bugs `/code-review`'s, privacy
`/data-privacy-review`'s; raise those only where they change a result.

This is a review. Do not change code, data or documents. Report findings; fix only if the user
asks afterwards.

## Scope

- With an argument: that path, branch diff, hypothesis family or stage.
- Without: the diff against `main` if it touches `src/enron_case/{clean,identity,network,finding,
  release,report}`, `config.py`, `docs/hypotheses*.md`, `docs/metrics.md` or `release/`;
  otherwise the whole analysis as published in `release/`.

## Rules for the reviewer itself

You are bound by the privacy promises of this project (`.specify/memory/constitution.md`,
Principles I and II).

- Never open, print or quote a raw message, the corpus archive, or anything in `data/raw` or
  `data/ingest`. Do not read rows of `data/restricted` either: it holds pseudonymized
  person-level data, and this review does not need it.
- Work from code, contracts, docs, git history, the counts files' fingerprints in the run
  manifest, the release tables in `release/`, and the synthetic corpus (`make sample`,
  `release-sample/`, `src/enron_case/synth/`). Recompute aggregates from release tables freely.
- If a check needs person-level data, write down the check and leave it to the lead; say so
  under "Not checked".
- Do not copy an address, a name or a pseudonym into your report.

## Sources

Read before checking: `specs/*/spec.md` (FR-005 … FR-018), `specs/*/research.md` (R3 dedupe, R4
identity, R6 zones, R8 reproducibility, R9 network, R10 hypotheses, R11 evidence, R12 risk),
`specs/*/data-model.md`, `specs/*/contracts/data-contracts.md`, `docs/metrics.md`,
`docs/hypotheses.md`, `docs/hypotheses-exploratory.md`, `docs/decision-record.md`,
`docs/ai-workflow-log.md` (what already went wrong and was caught), `release/report.md`, and the
`README.md` sections "Results in brief" and "Network science methods".

## Checks

Work through every group. For each check record pass, finding, not applicable or not checked,
with the evidence (`file:line`, table and column, or the number you recomputed).

### 1. Data flow and lineage

1. Each stage (`ingest` → `clean` → `identity` → `pseudo` → `network` → `finding` → `risk` →
   `release` → `report`) reads only the tables its contract lists and writes the columns the
   contract lists; no stage computes from data it should not see (e.g. a finding measure reading
   `messages` instead of `events`, or risk reading the address map outside the scorer).
2. Counts reconcile across stages: files seen → files parsed (rejected members counted, with
   reason) → header records → messages (exact and subset removals separately) → events
   (`in_network` true and false) → network ties per scope; addresses → entities by rule and by
   type (person, list, system, role, unknown). Recompute from `release/data_quality.csv` and the
   report; a step that drops data without a row is a finding.
3. Every exclusion is counted and its share reported: rejected files, missing sender or date,
   dates outside the plausible range, malformed addresses, no recipients, self-only, mass
   mailings above `recipient_cap`, non-person entities, weeks below `k_min`. FR-009 requires
   counts before and after each cleaning step; check `release/tables.py:data_quality` against
   the flags `clean/noise.py` computes.
4. The run manifest (`release/run_manifest.json`) records code version, parameters, seed, input
   corpus fingerprint and output fingerprints per table; null or missing fields are findings.
   `enron-case verify` (two runs, one key, identical fingerprints) was run on the code version
   that produced the release.

### 2. Cleaning decisions and their justification

For each rule below ask four questions: is the reason documented (research, contract or
`config.py` comment)? is its effect measured (count removed or merged; precision and recall on
synthetic truth; the manual merge sample)? could it bias the analysis (removes or merges more in
one period, one group or one side of a comparison)? does a published result depend on it, and if
so is there a sensitivity check?

| Rule | Where | What to look for |
|------|-------|------------------|
| Header allowlist and the content line | `contracts/header-allowlist.md`, `ingest/allowlist.py` | a dropped field an analysis would need; a kept field that smuggles content |
| Folder classes | `ingest/`, X-Folder ruling | whether sent-folder detection (N5, `is_custodian`) depends on folder names, and its error rate |
| Address normalisation | `clean/addresses.py` | case, quotes, `mailto:`, legacy directory forms; variants that survive as separate nodes |
| Malformed addresses | `bad_address` flag | count, and whether flagged messages still enter the network |
| Deduplication, exact and subset | `clean/dedupe.py`, research R3 | share removed (about half the files are copies); exact vs subset split; synthetic precision/recall; merges of distinct same-second messages; copies with clock differences that do not merge (see the timestamp defect in group 3) |
| Missing sender or date | `clean/`, `pseudo/` | dropped or kept, and counted |
| Mass-mailing cap | `recipient_cap`, `noise.py` | the flag counts addresses, the `cap=N` variant counts entities: same threshold, different unit |
| Plausible date range | `plausible_start/end`, `clean/dates.py` | messages outside it by period; the analysis window inside it |
| Identity rules N1–N4 and guards | `identity/rules.py`, research R4 | merges per rule; N2 across ISP subdomains; false merges that create hubs (inflate in-degree Gini, reciprocity, distinct contacts); whether the manual sample covers every rule and reports an interval, not only a point |
| Entity typing | `identity/classify.py` | persons typed as lists or roles (silently leave the network) and the reverse; counts by type |

### 3. Sampling and selection biases of this corpus

- Custodians are about 150 mostly senior mailboxes; results describe them, not the company.
- A tie is visible only when one end is a custodian; only the `core` scope is seen from both
  sides. Ego-level measures (an inbox, a sent folder) see one side.
- Retention and collection differ by person and period; volume and coverage rise toward late
  2001. Compare `volume` and `active_persons` in `release/weekly_metrics.csv` across every pair
  of windows a result compares; a measure that rises with retained volume is suspect.
- Known corpus defects found here: reference-year (2000) timestamps shifted by several hours;
  every Bcc line repeats the Cc line. Check every measure and rule that uses hour, weekday,
  second-level timestamps (dedupe key) or roles, not only the hypotheses already caveated.
- Inclusion thresholds (`exploratory_min_messages`, `min_unit_events`, `k_min`) select who is
  analysed; report how many units survive per comparison and whether the survivors differ
  between the test and its placebo.
- Every published result names the biases that could produce it, next to the result.

### 4. Hypotheses

1. Stated before the data or before computing: compare the commit that states each hypothesis
   (`git log -- docs/hypotheses*.md`) with the first commit that computes it or records its
   result (`git log -- src/enron_case/finding/ release/`). The text says when; the history
   must agree.
2. Direction, metric, scope, windows and decision rule fixed in advance; any later change is
   labelled as an amendment with its date and reason (`git diff <stating commit> HEAD -- docs/
   hypotheses*.md`), including changes to the statistic itself.
3. No hypothesis edited, dropped or re-scoped after its result; checks added after a result are
   labelled post hoc and applied to every hypothesis where the same threat exists, not only to
   the ones that passed.
4. Family size and correction honest: Holm across the whole family (H1–H4; H5–H25, recorded
   as E1–E21, as one family); the correction grows when hypotheses are added; a derived hypothesis (E11) is marked.
   Check that the data can reach significance at all after correction (units vs the smallest
   attainable Wilcoxon or permutation p).
5. No p-hacking by accretion: count families, hypotheses and post hoc checks over time in the
   workflow log; adding a family after a null result is acceptable only with the correction
   spanning all of them and the result labelled exploratory.

### 5. Statistical validity

- **Permutation test (CUSUM)**: assumes weeks exchangeable under no change; weekly series are
  autocorrelated, so p is optimistic. Was the false-support rate calibrated on autocorrelated
  synthetic series, or only on independent ones?
- **Change point estimated on the same data** as the effect: the effect after the maximising
  week is biased away from zero, and the block bootstrap holds the week fixed, so the interval
  ignores that selection. The null-model z and placebo are the guard; check they use the same
  selection.
- **Block bootstrap**: block length (`block_weeks`) against the series' autocorrelation; enough
  blocks in the baseline and after periods.
- **Paired designs and Wilcoxon**: zeros and ties (many measures are exactly 0 for most units);
  two-sided test against a directional claim; the bootstrap interval on the median with small n.
- **Effect sizes and intervals** reported for every outcome, not only p-values; units stated.
- **Null models test the named threat**: the volume-preserving null (c) reproduces in-degree
  concentration by construction (H1); check each null against the alternative it is meant to
  rule out.
- **Artifact checks** (baseline drift of frozen communities, composition, volume and retention):
  applied wherever the threat exists, including exploratory measures, not only where first
  noticed. A placebo that passes because its interval is wide (fewer units, less mail) is weak
  evidence: compare placebo n and power with the test's.
- **Leave-one-out and variants**: present for each published result; FR-017 requires
  robustness to cleaning thresholds (cap, dedupe, identity), so name the ones missing.
- **Sample sizes after filters** reported next to every result.

### 6. Interpretation

- Claims match evidence: no causal language from observational data; "confident" or "held
  true" only at the stated standard; exploratory and confirmatory results clearly separated in
  `README.md`, `docs/decision-record.md`, `docs/slides.md` and `release/report.md`.
- A measure's name does not claim more than it measures (e.g. "wrote back" for "also sent to the
  custodian in the same window").
- Every published result states its limits next to it, including measure-specific ones.
- Every number in the report, decision record, slides and README traces to a release table, or
  is clearly marked approximate; stale numbers from earlier runs in docs are findings.

### 7. Privacy-utility trade-off of the analysis

- Aggregation and k-suppression do not change what a result means (suppressed weeks dropped,
  not zero; medians over custodians not computed on suppressed cells).
- The utility loss of each mitigation (R1, R2) is reported as research R12 promises; an empty
  `utility_effect_ratio` or `finding_survives` needs a stated reason.

## Report

Output in this order:

1. **Verdict**: one line — `SOUND`, `SOUND WITH FINDINGS`, or `FLAWED` (a published claim is not
   supported by the evidence at the standard it states).
2. **Published claims**: one short paragraph: which claims in README, report and decision
   record stand, and which do not.
3. **Findings**, most severe first:

   | ID | Severity | Group | Location (`file:line` or table/column) | Flaw | How it could change a published result | Suggested check or fix |
   |----|----------|-------|----------------------------------------|------|----------------------------------------|------------------------|

   Severity: HIGH (a published claim may not hold), MEDIUM (a result's strength or a reported
   number may be wrong, or a required measurement is missing), LOW (documentation, labelling or
   a check that would not change a current result).
4. **Checks performed**: groups 1–7 with pass / finding / not applicable / not checked.
5. **Not checked**, and why (needs person-level data, needs a rerun, out of scope).

Separate what you confirmed (read in code, recomputed from a release table, seen in git history)
from what you infer. If the project keeps a workflow log (`docs/ai-workflow-log.md`), offer to
append a one-line summary of the review; do not write to it unasked.
