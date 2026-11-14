"""Checks against known artifacts, one per hypothesis whose main threat is not covered by the
pre-registered robustness checks (docs/hypotheses.md, "Artifact checks").

Added after the first real-data run showed that the pre-registered checks could not tell a
change in behaviour from two artifacts of the data:

- H2 `baseline_placebo`: communities frozen on a baseline go stale. Any partition fits best on
  the period it was fitted to, so cross-community share rises right after the baseline ends
  whether or not anything happened. The placebo fits communities on the first half of the
  baseline and measures the jump into the second half, a calm period before any 2001 event.
  If that out-of-sample jump is itself large, the test effect cannot be told apart from drift.
- H3 `within_custodian`: the aggregate external share moves when the mix of mailboxes holding
  mail changes. The check holds people fixed: the change in each custodian's own external share
  between the baseline and the period after the change point, summarised by the median.

A check that fails, or cannot run, caps the hypothesis at low confidence (select.py), so it
cannot be headline.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from datetime import date

import numpy as np
import polars as pl

from enron_case.config import CI_PERCENTILES, Config
from enron_case.contracts.vocab import DEFAULT_VARIANT, PERSON
from enron_case.finding import stats
from enron_case.finding.hypotheses import HYPOTHESES, Evidence, Network, Recompute, bootstrap_ci
from enron_case.network.communities import baseline_communities
from enron_case.network.snapshots import stable_sum

BASELINE_PLACEBO = "baseline_placebo"
WITHIN_CUSTODIAN = "within_custodian"
CHECK_FOR = {"H2": BASELINE_PLACEBO, "H3": WITHIN_CUSTODIAN}

# Stream labels of the two checks' generators, apart from those in hypotheses.py.
_PLACEBO_STREAM = 7
_WITHIN_CUSTODIAN_STREAM = 8


@dataclass(frozen=True)
class ArtifactCheck:
    hypothesis: str
    check: str
    statistic: float
    ci_low: float
    ci_high: float
    n_units: int
    passes: bool | None
    note: str


def run_checks(
    evidence: list[Evidence], network: Network, recompute: Recompute, config: Config
) -> list[ArtifactCheck]:
    by_id = {e.hypothesis.id: e for e in evidence}
    out = []
    for hyp in HYPOTHESES:
        check = CHECK_FOR.get(hyp.id)
        if check == BASELINE_PLACEBO:
            out.append(baseline_placebo(network, recompute, config))
        elif check == WITHIN_CUSTODIAN:
            out.append(within_custodian(network, by_id[hyp.id].change_week, config))
    return out


def baseline_placebo(network: Network, recompute: Recompute, config: Config) -> ArtifactCheck:
    """Fit communities on the first half of the baseline; effect of the second half."""
    mid = config.baseline_start + (config.baseline_end - config.baseline_start) / 2
    placebo = dataclasses.replace(config, baseline_end=mid)
    communities = baseline_communities(network.events, network.entities_p, placebo)
    series = recompute(network.events, network.entities_p, communities, placebo)
    values = series.filter(
        (pl.col("metric") == "cross_community_share")
        & (pl.col("scope") == "observed")
        & (pl.col("variant") == DEFAULT_VARIANT)
        & pl.col("value").is_not_null()
    )
    before = _values(values, config.baseline_start, mid)
    after = _values(values, mid + _ONE_DAY, config.baseline_end)
    try:
        effect = stats.effect_size(before, after, min_baseline_weeks=config.min_baseline_weeks)
        low, high = bootstrap_ci(before, after, config, stats.rng_for(config.seed, _PLACEBO_STREAM))
    except stats.InsufficientData:
        return ArtifactCheck(
            "H2",
            BASELINE_PLACEBO,
            math.nan,
            math.nan,
            math.nan,
            len(before) + len(after),
            None,
            "placebo periods too short",
        )
    # Drift alone would otherwise produce "changes" of the size being tested.
    passes = abs(effect) <= config.placebo_max_effect
    note = (
        "out-of-sample jump within the calm baseline year is small"
        if passes
        else "a calm half-year out of sample already jumps: the test effect is baseline drift"
    )
    return ArtifactCheck(
        "H2", BASELINE_PLACEBO, effect, low, high, len(before) + len(after), passes, note
    )


def within_custodian(network: Network, change_week: date | None, config: Config) -> ArtifactCheck:
    """Median within-custodian change in external share, baseline vs after the change point."""
    if change_week is None:
        return ArtifactCheck(
            "H3",
            WITHIN_CUSTODIAN,
            math.nan,
            math.nan,
            math.nan,
            0,
            None,
            "no change point, nothing to check",
        )
    custodians = network.entities_p.filter(pl.col("is_custodian")).get_column("pid")
    sent = network.events.filter(
        pl.col("in_network")
        & (pl.col("sender_type") == PERSON)
        & (pl.col("recipient_type") == PERSON)
        & pl.col("sender_internal")
        & pl.col("sender_pid").is_in(custodians.implode())
    ).with_columns(pl.col("ts_hour").dt.date().alias("day"))
    # A minimum of sent events per period keeps one person's share from being decided by a
    # handful of messages.
    before = _shares(sent, config.baseline_start, config.baseline_end, config.min_unit_events)
    after = _shares(sent, change_week, config.analysis_end, config.min_unit_events)
    # Sorted, so the seeded bootstrap resamples the same order on every run.
    paired = before.join(after, on="sender_pid", suffix="_after").sort("sender_pid")
    changes = (paired.get_column("share_after") - paired.get_column("share")).to_numpy()
    n = len(changes)
    if n < config.k_min:
        return ArtifactCheck(
            "H3",
            WITHIN_CUSTODIAN,
            math.nan,
            math.nan,
            math.nan,
            n,
            None,
            "fewer custodians than the minimum group size",
        )
    rng = stats.rng_for(config.seed, _WITHIN_CUSTODIAN_STREAM)
    medians = np.median(rng.choice(changes, size=(config.bootstrap_reps, n)), axis=1)
    quantiles = [percentile / 100 for percentile in CI_PERCENTILES]
    low, high = (float(q) for q in np.quantile(medians, quantiles))
    passes = stats.on_side(-1, low, high)  # H3 direction: down
    note = (
        "custodians themselves shifted their mail inward"
        if passes
        else "no within-custodian change: the aggregate shift is a change in who is in the data"
    )
    return ArtifactCheck(
        "H3", WITHIN_CUSTODIAN, float(np.median(changes)), low, high, n, passes, note
    )


def table(checks: list[ArtifactCheck]) -> pl.DataFrame:
    rows = [dataclasses.asdict(c) for c in checks]
    return pl.DataFrame(
        rows,
        schema={
            "hypothesis": pl.String(),
            "check": pl.String(),
            "statistic": pl.Float64(),
            "ci_low": pl.Float64(),
            "ci_high": pl.Float64(),
            "n_units": pl.Int64(),
            "passes": pl.Boolean(),
            "note": pl.String(),
        },
    )


def failed(checks: list[ArtifactCheck]) -> set[str]:
    """Hypotheses whose artifact check did not pass: it failed (`passes` False) or could not
    run (`passes` None). Both cap confidence, because an artifact not ruled out may explain the
    change; the table keeps the two apart."""
    return {c.hypothesis for c in checks if c.passes is not True}


_ONE_DAY = date(2000, 1, 2) - date(2000, 1, 1)


def _values(series: pl.DataFrame, start: date, end: date) -> stats.FloatArray:
    picked = series.filter((pl.col("week") >= start) & (pl.col("week") <= end)).sort("week")
    out: stats.FloatArray = picked.get_column("value").to_numpy().astype(float)
    return out


def _shares(sent: pl.DataFrame, start: date, end: date, min_events: int) -> pl.DataFrame:
    return (
        sent.filter((pl.col("day") >= start) & (pl.col("day") <= end))
        .group_by("sender_pid")
        .agg(
            stable_sum((~pl.col("recipient_internal")).cast(pl.Float64) * pl.col("weight")).alias(
                "ext"
            ),
            stable_sum(pl.col("weight")).alias("w"),
            pl.len().alias("n"),
        )
        .filter(pl.col("n") >= min_events)
        .select("sender_pid", (pl.col("ext") / pl.col("w")).alias("share"))
    )
