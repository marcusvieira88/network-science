# WP-F Finding: hypotheses, statistics, headline

**Tasks**: T053–T059. **Owns**: `src/enron_case/finding/`, `tests/unit/finding/`,
`docs/hypotheses.md`. **Stage function**: `finding/stage.py: run(ctx)`.
**Reads**: `metric_series`, `snapshots`, `events`, `entities_p`, `communities`.
**Writes**: `hypothesis_results`.

Write `docs/hypotheses.md` first: H1–H4 exactly as research R10 (metric, scope, direction,
baseline period, decision rule, what would falsify each).

| ID | Metric | Scope | Direction |
|----|--------|-------|-----------|
| H1 | indegree_gini | core | up |
| H2 | cross_community_share | observed | up |
| H3 | external_share | observed | down |
| H4 | tie_turnover | core | up |

## Statistics (`stats.py`, all seeded from `config.seed`)

- Change point: CUSUM on the series over `analysis_start..end`; p-value by permuting weeks
  (`config.permutations`).
- Effect: standardised difference, (mean after change − mean of baseline) / sd of baseline.
- Interval: moving-block bootstrap (`config.bootstrap_reps`, block 4 weeks), 95%.
- Holm correction across H1–H4.
- Public interface used by WP-G:
  `def effect_size(before: np.ndarray, after: np.ndarray) -> float`.

## Robustness (`hypotheses.py`)

- Null model (`nullmodel.py`): within each week rewire recipients preserving every sender's
  out-weight and every recipient's in-weight; `null_z` = (observed − mean null) / sd null.
- Leave-one-mailbox-out: recompute the metric excluding each custodian pid; report min and max
  effect. Variants: re-estimate on each `variant` present in `metric_series`.
- Recomputing a metric uses `enron_case.network.metrics.compute_series` (WP-E, signature in
  `docs/agents/WP-E.md`). Until that exists, take the recompute function as a parameter and
  inject a fake in tests; the stage imports the real one.
- Support and confidence rule exactly as written in `docs/metrics.md` (WP-E writes it; until
  then use research R11: high = passes change point, effect interval excluding 0, null model,
  all LOO same sign, all variants, Holm p < 0.05). At most one `is_headline`: the supported
  hypothesis with the largest effect. "None supported" is a valid result.

## Acceptance

- CUSUM recovers a planted step within one window; false-positive rate ≤ 5% on no-change
  series across seeds; bootstrap covers a known effect; Holm matches a worked example.
- On the fixture `metric_series` (planted), H1 and H2 come out supported; on `synth_nochange`
  none does. Always exactly four rows.
