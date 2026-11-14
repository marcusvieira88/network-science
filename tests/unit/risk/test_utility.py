"""Utility of a release: headline effect recomputed from what the variant exposes."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from enron_case.config import Config
from enron_case.finding import stats
from enron_case.risk import utility

CONFIG = Config()
CHANGE = date(2001, 8, 13)


def effect_size(before: np.ndarray, after: np.ndarray) -> float:
    return float((np.mean(after) - np.mean(before)) / np.std(before, ddof=1))


def baseline_effect(before: np.ndarray, after: np.ndarray) -> float:
    """The finding's effect size with the configured minimum baseline."""
    return stats.effect_size(before, after, min_baseline_weeks=CONFIG.min_baseline_weeks)


def series(values: dict[date, float | None]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "scope": "core",
            "week": list(values),
            "metric": "indegree_gini",
            "value": list(values.values()),
            "variant": "default",
        }
    )


def weeks(start: date, n: int) -> list[date]:
    return [start + timedelta(days=7 * i) for i in range(n)]


HEADLINE = utility.Headline("indegree_gini", "core", CHANGE)


def test_find_headline() -> None:
    table = pl.DataFrame(
        {
            "metric": ["indegree_gini", "external_share"],
            "scope": ["core", "observed"],
            "change_week": [CHANGE, None],
            "is_headline": [True, False],
        }
    )
    assert utility.find_headline(table) == HEADLINE
    assert utility.find_headline(table.with_columns(pl.lit(False).alias("is_headline"))) is None


def test_split_uses_baseline_and_post_change_weeks_and_drops_suppressed() -> None:
    values: dict[date, float | None] = dict.fromkeys(weeks(date(2000, 1, 3), 52), 1.0)
    values[date(2000, 1, 3)] = None
    values.update(dict.fromkeys(weeks(CHANGE - timedelta(days=14), 2), 9.0))  # neither side
    values.update(dict.fromkeys(weeks(CHANGE, 4), 2.0))
    before, after = utility.split_series(series(values), HEADLINE, CONFIG)
    assert before.size == 51 and set(before) == {1.0}
    assert after.tolist() == [2.0] * 4


def test_effect_and_interval_on_known_step() -> None:
    rng = np.random.default_rng(3)
    before = 1.0 + rng.normal(0, 0.1, 50)
    after = 2.0 + rng.normal(0, 0.1, 30)
    effect = utility.effect_with_interval(before, after, effect_size, reps=300, seed=1)
    assert effect is not None
    assert effect.value == pytest.approx(effect_size(before, after))
    assert effect.ci_low > 0 and effect.ci_low <= effect.value <= effect.ci_high


def test_effect_not_computable_without_data() -> None:
    one_week = np.array([1.0])
    assert utility.effect_with_interval(one_week, one_week, effect_size, 10, 1) is None


def test_draws_with_a_constant_baseline_are_skipped_not_fatal() -> None:
    # Two of three baseline weeks are equal: many bootstrap draws repeat one value and the real
    # effect_size raises InsufficientData on them; the interval comes from the other draws.
    before = np.array([1.0, 1.0, 2.0])
    after = np.array([5.0, 6.0, 7.0])
    effect = utility.effect_with_interval(before, after, baseline_effect, reps=200, seed=3)
    assert effect is not None
    assert effect.value == pytest.approx((6.0 - 4.0 / 3.0) / np.std(before, ddof=1))
    assert effect.ci_low > 0


def test_constant_baseline_gives_no_effect() -> None:
    before = np.array([2.0, 2.0, 2.0])
    after = np.array([5.0, 6.0])
    assert utility.effect_with_interval(before, after, baseline_effect, reps=20, seed=1) is None


def test_compare() -> None:
    base = utility.Effect(2.0, 1.0, 3.0)
    assert utility.compare(base, base) == utility.Utility(1.0, True)
    assert utility.compare(base, utility.Effect(1.0, -0.5, 2.5)) == utility.Utility(0.5, False)
    assert utility.compare(base, utility.Effect(-1.0, -2.0, -0.5)) == utility.Utility(-0.5, False)
    assert utility.compare(base, None) == utility.Utility(None, False)
    assert utility.compare(None, base) == utility.NOT_APPLICABLE
