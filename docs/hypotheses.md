# Hypotheses H1–H4

Written and committed **before any analysis of the real corpus** (FR-016, research R10), so
H1–H4 carry the timing label "pre-registered". The
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
  (`config.min_after_weeks`) after it. The "after" period runs from the change week to the end of the analysis window.
- Weeks where the metric is undefined (fewer than `config.k_min` active persons) are dropped,
  not treated as zero.

## Decision rule (same for every hypothesis)

Let `d` = +1 for "up" and −1 for "down". Significance level α = 0.05 (`config.alpha`).

1. **Change point (a)**: weighted directional CUSUM over the analysis window of `n` weeks,
   `T = max over candidate weeks τ of −d · Σ_{i<τ}(x_i − mean x) · √(n / (τ (n − τ)))`. The
   change week is the maximising τ. (The weight keeps changes near the end of the window from
   being under-scored.) p-value `p_perm` by permuting the weeks (`config.permutations` permutations,
   seeded from `config.seed`), `p = (1 + #{T_perm ≥ T}) / (1 + permutations)`.
2. **Effect (b)**: `effect = (mean after change − mean baseline) / sd baseline` (sample sd).
   95% interval `ci_low .. ci_high` (`config.ci_level`) by moving-block bootstrap (blocks of
   4 weeks, `config.block_weeks`; `config.bootstrap_reps` replicates, resampling baseline and
   after period separately, change week held fixed).
3. **Multiple testing (f)**: Holm correction of `p_perm` across H1–H4 gives `p_holm`.

`supported` is decided in this order:

- **inconclusive** if the effect cannot be computed (fewer than two baseline weeks,
  `config.min_baseline_weeks`; a constant baseline; or fewer than four weeks,
  `config.min_after_weeks`, after every candidate change point);
- **no** if the interval lies wholly on the opposite side of zero (both `d · ci_low < 0` and `d · ci_high < 0`);
- **yes** if `p_holm < α` and the interval lies wholly on the hypothesised side (both `d · ci_low > 0` and `d · ci_high > 0`);
- **no** if `p_holm ≥ α` and the interval does not lie wholly on the hypothesised side;
- **inconclusive** otherwise (the change-point test and the interval disagree).

`change_week` is reported only when `p_holm < α`. A hypothesis whose effect cannot be computed
enters the Holm correction with `p_perm = 1`, and its effect and interval are reported as NaN.

*Amendment to the statistic, made after the hypotheses were stated and before any real-data run
of the network or finding stage:* the hypotheses were first committed (4c19702, 2026-11-14
11:33) with the unweighted CUSUM `T = max_τ −d · Σ_{i<τ}(x_i − mean x)`. The weight
`√(n / (τ (n − τ)))` was added in 7ab70d4 (11:42), with the implementation, because on
synthetic series the unweighted statistic mislocates changes late in the window. The only
real-data run before it (78f18ed, 11:41) stopped before the network stage, so no real metric
series existed; the first real-data finding run is 57dff81 (12:03). The p = 1 rule for an
undefined estimate and the 20 null replicates were added in the same commit. History:
`git log -- docs/hypotheses.md`.

## Robustness checks

- **Null model (c)**: within each week, recipients are shuffled among events of equal weight,
  equal `in_network` flag and the same kind of sender (type and internal flag), which preserves
  every sender's out-weight and every recipient's in-weight from each kind of sender in that
  week. The metric series is recomputed on each of 20 (`config.null_replicates`) rewired
  networks and each replicate's effect taken at its own searched change week (amended; see
  below). `null_z = (effect − mean null effect) / sd null effect`.
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

*Amendment to the null model, made after every real-data result was known (review of
2026-11-14):* two defects made `null_z` optimistic, and both are fixed. (1) Recipients were
shuffled among events of equal week, weight and `in_network` flag only, so a recipient could
trade a person's message for a list's or an outsider's; the network is built from ties sent by
internal persons, so in-weight *from persons* was not preserved. The stratum now also holds the
sender's type and internal flag. (2) Each null replicate's effect was taken at the observed
change week, while the observed effect is the maximum over candidate weeks; each replicate now
searches its own change week with the same CUSUM. Both changes make the null harder to beat
(they are expected to lower `null_z`, though the null's standard deviation also changes, so not
guaranteed to). They change no published outcome: no hypothesis among H1–H4 is held true either way. With the
corrected null, H3's `null_z` moves from −4.7 to +2.0, so H3 now also fails the null-model check
(its change is reproduced by rewiring with the same volumes); H2's stays far above the threshold
and is explained by its artifact check instead.

## Confidence and headline

Confidence rule (research R11; `docs/metrics.md` restates it, and the two must agree):

- **high**: `supported = yes` and all three robustness checks (c), (d), (e) pass;
- **moderate**: `supported = yes` and exactly one of (c), (d), (e) fails;
- **low**: `supported = yes` with two or more checks failing, or `supported` is no or
  inconclusive.

**Headline** (research R10): of the hypotheses with `supported = yes` that pass every
robustness check (confidence high), the one with the largest effect in its hypothesised direction
(`d · effect`); ties go to the lower ID. At most one headline; none when no supported hypothesis
passes every check, in which case the supported ones are still reported with their confidence.

*Amendment, made before the first real-data run of the finding stage:* the headline rule above
replaces "largest supported effect" so that it matches the pre-registered rule in research R10.

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
  *Calibration (added after the data-science review):* on 1,000 simulated 117-week series (the
  full weeks of the analysis window; the published series has 118 weekly rows, because the week
  of 1999-12-27 holds 1 and 2 January 2000) with
  no change, the test at α = 0.05 rejects 3.2 % of independent series, but 14.8 % of AR(1)
  series with φ = 0.3 and 25.6 % with φ = 0.5 (`tests/unit/finding/test_stats.py`,
  `test_permutation_test_is_liberal_on_autocorrelated_no_change`). Weekly network metrics are
  autocorrelated, so `p_perm` and `p_holm` overstate significance; a small p alone is weak
  evidence here. No H1–H4 finding is claimed, so this changes no published conclusion, but it is
  one more reason the supported H2 and H3 needed the artifact checks.
- The null model preserves in-weight per person per week, so in-degree concentration (H1) is
  largely reproduced by the null by construction; H1 will rarely pass (c) and so rarely reach
  high confidence. This is reported, not tuned away.

## Artifact checks (added after the first real-data run)

**This section was written after seeing real results, and says so.** On the first real run, H2
(+13.8 standard deviations) and H3 passed every pre-registered check. Two diagnostics run by the
lead before accepting either showed the pre-registered checks could not tell a behavioural change
from two known artifacts:

- **H2, `baseline_placebo`.** Communities fixed on a baseline go stale, and any partition fits
  best on the period it was fitted to, so cross-community share rises right after the baseline
  ends whatever happens. Placebo: fit communities on the first half of the baseline year and
  measure the jump into the calm second half (out of sample, before any 2001 event). A jump of
  more than `config.placebo_max_effect` (2.0) baseline standard deviations fails: drift alone then
  produces effects of the size being tested.
- **H3, `within_custodian`.** The aggregate external share moves when the mix of mailboxes
  holding mail changes. The check holds people fixed: the median, over custodians with at least
  30 (`config.min_unit_events`) sent events in both periods, of the change in each custodian's own external share between
  the baseline and the period after the change point. Passes only if its bootstrap interval lies
  below zero (the hypothesised direction).

*Coverage (noted in the pre-delivery review, post hoc).* `cross_community_share` leaves out
every tie touching a person with no tie in 2000 (community −1). Their share grows through 2001:
in the crisis weeks about two-thirds of the messages in the published group graph
(`release/community_graph.csv`, group `other`) touch them. H2 therefore measures crossings among
people already active in 2000, a shrinking part of the mail; this is one more reason it is not a
finding, and any group-level reading of 2001 describes that part only.

A failed check caps the hypothesis at **low** confidence, so it cannot be the headline. A check
that could not run (for example `within_custodian` without a change point) caps it too, because
the artifact is then not ruled out; it is reported as "not run", not as a pass. H1 and H4
have no artifact check: neither was supported. The checks are in `src/enron_case/finding/
artifacts.py`, their results in `release/artifact_checks.csv`, and both are tested on synthetic
data where groups do not drift and the planted change is behavioural (both checks pass there).

## Further hypotheses H5–H26

Twenty further hypotheses, H5–H24, continue this numbering. They were stated by the project
owner after the results of H1–H4 and committed before each was computed; their timing label is
"stated before computed, after earlier results". Two more are "post hoc", stated after every
other result was known and before being computed: H25, a replication test of prior work, and
H26, a structural question (did custodians leave during the crisis?). Definitions, windows and
decision rules are in `docs/hypotheses-exploratory.md` (recorded there as E1–E21, E*n* = H*n*+4,
and O1 = H26). Holm's correction runs across H5–H25; H26 has its own rule with a Bonferroni
bound over all twenty-six (`config.HYPOTHESES_STATED`).
