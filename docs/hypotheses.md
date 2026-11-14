# Hypotheses H1–H4

Written and committed **before any analysis of the real corpus** (FR-016, research R10). The
hypotheses, their metrics, directions, periods and decision rules below are fixed. A change to
any of them after real-data results exist must be logged in `docs/ai-workflow-log.md` with the
reason, and the original version stays in the git history.

All four outcomes are published, whatever they are. "None supported" is an acceptable result.
Public event dates (CEO resignation in August 2001, the October loss announcement, the December
filing) annotate the series only; they are never used to choose windows or change points.

## The hypotheses

| ID | Claim | Metric | Scope | Direction |
|----|-------|--------|-------|-----------|
| H1 | Communication concentrated on fewer people as the crisis approached | `indegree_gini` | core | up |
| H2 | Communication increasingly crossed established group boundaries | `cross_community_share` (communities frozen on the 2000 baseline) | observed | up |
| H3 | The organization turned inward | `external_share` | observed | down |
| H4 | Working relationships were rewired faster | `tie_turnover` | core | up |

Metric definitions are in `docs/metrics.md`. Scope `core` = both ends are custodians (mailbox
owners); scope `observed` = every internal person seen in the headers.

## Periods

- **Analysis window**: `config.analysis_start .. config.analysis_end` (2000-01-01 .. 2002-03-31).
- **Baseline**: `config.baseline_start .. config.baseline_end` (calendar 2000).
- **Change point**: searched only among weeks after the baseline, leaving at least four weeks
  after it. The "after" period runs from the change week to the end of the analysis window.
- Weeks where the metric is undefined (fewer than `config.k_min` active persons) are dropped,
  not treated as zero.

## Decision rule (same for every hypothesis)

Let `d` = +1 for "up" and −1 for "down". Significance level α = 0.05.

1. **Change point (a)**: directional CUSUM over the analysis window,
   `T = max over candidate weeks τ of −d · Σ_{i<τ}(x_i − mean x)`. The change week is the
   maximising τ. p-value `p_perm` by permuting the weeks (`config.permutations` permutations,
   seeded from `config.seed`), `p = (1 + #{T_perm ≥ T}) / (1 + permutations)`.
2. **Effect (b)**: `effect = (mean after change − mean baseline) / sd baseline` (sample sd).
   95% interval `ci_low .. ci_high` by moving-block bootstrap (blocks of 4 weeks,
   `config.bootstrap_reps` replicates, resampling baseline and after period separately, change
   week held fixed).
3. **Multiple testing (f)**: Holm correction of `p_perm` across H1–H4 gives `p_holm`.

`supported` is decided in this order:

- **inconclusive** if the effect cannot be computed (fewer than two baseline weeks, a constant
  baseline, or fewer than four weeks after every candidate change point);
- **no** if the interval lies wholly on the opposite side of zero (`d · ci_high < 0`);
- **yes** if `p_holm < α` and the interval lies wholly on the hypothesised side (`d · ci_low > 0`);
- **no** if `p_holm ≥ α` and the interval does not lie wholly on the hypothesised side;
- **inconclusive** otherwise (the change-point test and the interval disagree).

`change_week` is reported only when `p_holm < α`.

## Robustness checks

- **Null model (c)**: within each week, recipients are shuffled among events of equal weight
  and equal `in_network` flag, which preserves every sender's out-weight and every recipient's
  in-weight in that week. The metric series is recomputed on each rewired network and the
  effect taken at the same change week. `null_z = (effect − mean null effect) / sd null effect`.
  Passes when `d · null_z > z_{1−α}` (one-sided, 1.645). A change that the volume-preserving
  null reproduces is a volume or degree change, not a structural one.
- **Leave-one-mailbox-out (d)**: the series is recomputed without each custodian in turn and the
  effect taken at the same change week; `loo_min_effect`, `loo_max_effect` report the range.
  Passes when every leave-one-out effect has the hypothesised sign.
- **Variants (e)**: every non-default `variant` present in `metric_series` (recipient cap,
  window length) is re-estimated from scratch (own change point, own interval). A variant passes
  when its own `p_perm < α` and its interval lies wholly on the hypothesised side.
  `robust_variants_passed / robust_variants_total`. Passes when at least one variant exists and
  all pass.

## Confidence and headline

Confidence rule (research R11, until `docs/metrics.md` states it; the two must agree):

- **high**: `supported = yes` and all three robustness checks (c), (d), (e) pass;
- **moderate**: `supported = yes` and exactly one of (c), (d), (e) fails;
- **low**: `supported = yes` with two or more checks failing, or `supported` is no or
  inconclusive.

**Headline**: of the hypotheses with `supported = yes`, the one with the largest effect in its
hypothesised direction (`d · effect`); ties go to the lower ID. At most one headline; none when
nothing is supported. Its confidence is reported next to it.

## What would falsify each

| ID | Falsified (outcome `no`) when | Main alternative explanations to state next to the result |
|----|-------------------------------|------------------------------------------------------------|
| H1 | Core in-degree Gini after the change is not above the 2000 baseline, or the rise is within chance | Retention: late-2001 mailboxes hold more mail for fewer people; a few departures shrink the core |
| H2 | Cross-community share does not rise above baseline | Communities from 2000 decay with reorganisation and staff turnover, so cross share rises mechanically |
| H3 | External share does not fall below baseline | External mail may be under-retained or deleted more often; investigation-shaped collection |
| H4 | Core tie turnover does not rise above baseline | Turnover rises with any change in volume or coverage, not only with restructuring |

## Known threats (state next to every result)

- Mailbox retention differs by person and period; volume and coverage rise toward late 2001 for
  reasons unrelated to behaviour.
- The custodians are senior staff, not a random sample.
- The collection was shaped by an investigation.
- The permutation test assumes weeks are exchangeable under no change; serial correlation in a
  weekly series makes it optimistic. The block bootstrap interval partly offsets this.
- The null model preserves in-weight per person per week, so in-degree concentration (H1) is
  largely reproduced by the null by construction; H1 will rarely pass (c) and so rarely reach
  high confidence. This is reported, not tuned away.
