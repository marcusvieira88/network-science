"""What a release variant costs the analysis: the headline effect recomputed from the data the
variant exposes, relative to the effect on the restricted data.

The effect itself is WP-F's `finding.stats.effect_size`, passed in. Its interval here is a
seeded percentile bootstrap over weeks, resampling the baseline and post-change weeks
independently.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import numpy as np
import polars as pl

from enron_case.config import Config
from enron_case.contracts.vocab import DEFAULT_VARIANT
from enron_case.finding.stats import InsufficientData

EffectFn = Callable[[np.ndarray, np.ndarray], float]

CI_LOW_PERCENTILE = 2.5
CI_HIGH_PERCENTILE = 97.5


@dataclass(frozen=True)
class Headline:
    metric: str
    scope: str
    change_week: date


@dataclass(frozen=True)
class Effect:
    value: float
    ci_low: float
    ci_high: float


@dataclass(frozen=True)
class Utility:
    effect_ratio: float | None
    finding_survives: bool | None


NOT_APPLICABLE = Utility(effect_ratio=None, finding_survives=None)


def find_headline(hypotheses: pl.DataFrame) -> Headline | None:
    """The headline hypothesis, if one is supported and has a change week."""
    rows = hypotheses.filter(pl.col("is_headline") & pl.col("change_week").is_not_null())
    if rows.height == 0:
        return None
    row = rows.row(0, named=True)
    return Headline(metric=row["metric"], scope=row["scope"], change_week=row["change_week"])


def split_series(
    series: pl.DataFrame, headline: Headline, config: Config
) -> tuple[np.ndarray, np.ndarray]:
    """Baseline-period values and values from the change week on, for the headline series.
    Suppressed (null) weeks are dropped."""
    values = series.filter(
        (pl.col("scope") == headline.scope)
        & (pl.col("metric") == headline.metric)
        & (pl.col("variant") == DEFAULT_VARIANT)
        & pl.col("value").is_not_null()
    )
    before = values.filter(
        pl.col("week").is_between(config.baseline_start, config.baseline_end)
    ).get_column("value")
    after = values.filter(
        pl.col("week").is_between(headline.change_week, config.analysis_end)
    ).get_column("value")
    return before.to_numpy(), after.to_numpy()


def effect_with_interval(
    before: np.ndarray, after: np.ndarray, effect_size: EffectFn, reps: int, seed: int
) -> Effect | None:
    """Effect and bootstrap interval, or None when the effect is not defined on the data (too
    few weeks, a constant baseline) or on any bootstrap draw. A draw on which it is not defined
    (for example, every resampled baseline week equal) is skipped, not fatal."""
    if before.size < 2 or after.size < 1:
        return None
    try:
        value = effect_size(before, after)
    except InsufficientData:
        return None
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(reps):
        resampled_before = rng.choice(before, size=before.size, replace=True)
        resampled_after = rng.choice(after, size=after.size, replace=True)
        try:
            draws.append(effect_size(resampled_before, resampled_after))
        except InsufficientData:
            continue
    finite = np.asarray([d for d in draws if np.isfinite(d)], dtype=np.float64)
    if finite.size == 0:
        return None
    return Effect(
        value=value,
        ci_low=float(np.percentile(finite, CI_LOW_PERCENTILE)),
        ci_high=float(np.percentile(finite, CI_HIGH_PERCENTILE)),
    )


def compare(restricted: Effect | None, variant: Effect | None) -> Utility:
    """Ratio of variant to restricted effect; the finding survives when the variant effect has
    the same sign and its interval excludes 0. A variant from which the effect cannot be
    recomputed loses the finding."""
    if restricted is None or restricted.value == 0.0:
        return NOT_APPLICABLE
    if variant is None:
        return Utility(effect_ratio=None, finding_survives=False)
    same_sign = np.sign(variant.value) == np.sign(restricted.value)
    excludes_zero = variant.ci_low > 0.0 or variant.ci_high < 0.0
    return Utility(
        effect_ratio=variant.value / restricted.value,
        finding_survives=bool(same_sign and excludes_zero),
    )
