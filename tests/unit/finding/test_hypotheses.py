"""Evidence gathering on generated metric series with a known answer."""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from enron_case.config import Config
from enron_case.contracts import vocab as v
from enron_case.errors import ContractViolation
from enron_case.finding import hypotheses, select

FAST = dataclasses.replace(Config(), permutations=199, bootstrap_reps=199)
VARIANTS = ("default", "cap=20")
EMPTY = pl.DataFrame()


def _weeks(config: Config) -> list[date]:
    week = config.analysis_start - timedelta(days=config.analysis_start.weekday())
    out = []
    while week <= config.analysis_end:
        out.append(week)
        week += timedelta(days=7)
    return out


def _series(seed: int, step: float = 0.0, change: date = date(2001, 8, 13)) -> pl.DataFrame:
    """iid unit noise per (scope, metric, variant); `step` added from `change` on, in each
    hypothesis' direction."""
    rng = np.random.default_rng(seed)
    weeks = _weeks(FAST)
    after = np.array([w >= change for w in weeks])
    direction = {h.metric: h.direction for h in hypotheses.HYPOTHESES}
    frames = []
    for scope in v.SCOPES:
        for metric in v.METRICS:
            for variant in VARIANTS:
                values = rng.normal(0.0, 1.0, len(weeks)) + direction.get(metric, 0) * step * after
                frames.append(
                    pl.DataFrame(
                        {
                            "scope": scope,
                            "week": weeks,
                            "metric": metric,
                            "value": values,
                            "n_active": 40,
                            "variant": variant,
                        }
                    )
                )
    return pl.concat(frames)


def _same_series(series: pl.DataFrame) -> hypotheses.Recompute:
    def recompute(
        events: pl.DataFrame,
        entities_p: pl.DataFrame,
        communities: pl.DataFrame,
        config: Config,
        variant: str = "default",
        exclude_pids: frozenset[str] = frozenset(),
    ) -> pl.DataFrame:
        return series.filter(pl.col("variant") == variant)

    return recompute


def _gather(series: pl.DataFrame) -> list[hypotheses.Evidence]:
    network = hypotheses.Network(_events(), _custodians(), EMPTY)
    return hypotheses.gather(series, network, _same_series(series), FAST)


def _events() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts_hour": [datetime(2001, 1, 1, tzinfo=UTC)],
            "in_network": [True],
            "weight": [1.0],
            **{c: ["x"] for c in ("recipient_pid", "recipient_type", "recipient_org_pid")},
            "recipient_internal": [True],
        }
    )


def _custodians() -> pl.DataFrame:
    return pl.DataFrame({"pid": ["a", "b"], "is_custodian": [True, True]})


def test_family_wise_false_support_rate_on_no_change_worlds() -> None:
    worlds = 100
    with_support = 0
    for seed in range(worlds):
        table = select.results_table(_gather(_series(seed)), FAST)
        with_support += "yes" in table.get_column("supported").to_list()
    tolerance = 2 * np.sqrt(0.05 * 0.95 / worlds)
    assert with_support / worlds <= 0.05 + tolerance


def test_planted_step_in_every_hypothesis_is_supported_and_robust() -> None:
    evidence = _gather(_series(1, step=2.0))
    table = select.results_table(evidence, FAST)
    assert table.get_column("supported").to_list() == ["yes"] * 4
    weeks = table.get_column("change_week").to_list()
    assert all(abs((w - date(2001, 8, 13)).days) <= 7 for w in weeks)
    assert [e.loo_effects == (e.effect, e.effect) for e in evidence] == [True] * 4
    assert [(e.variants_passed, e.variants_total) for e in evidence] == [(1, 1)] * 4


def test_undefined_weeks_are_dropped_not_zeroed() -> None:
    series = _series(2, step=2.0)
    holes = series.with_columns(
        pl.when(pl.col("week").dt.month() == 3).then(None).otherwise(pl.col("value")).alias("value")
    )
    hyp = hypotheses.HYPOTHESES[0]
    full = hypotheses.series_of(series, hyp, "default", FAST)
    holed = hypotheses.series_of(holes, hyp, "default", FAST)
    assert len(holed.weeks) < len(full.weeks)
    assert all(w.month != 3 for w in holed.weeks)


def test_series_without_any_defined_week_is_inconclusive() -> None:
    series = _series(3).with_columns(
        pl.when(pl.col("metric") == "tie_turnover")
        .then(None)
        .otherwise(pl.col("value"))
        .alias("value")
    )
    table = select.results_table(_gather(series), FAST)
    h4 = table.row(3, named=True)
    assert (h4["supported"], h4["confidence"], h4["p_perm"]) == ("inconclusive", "low", 1.0)
    assert np.isnan(h4["effect"])


def test_missing_metric_is_a_contract_violation() -> None:
    series = _series(4).filter(pl.col("metric") != "external_share")
    with pytest.raises(ContractViolation):
        _gather(series)
