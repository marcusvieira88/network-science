"""H1–H4 bound to metric and scope, and the evidence gathered for each (docs/hypotheses.md).

Recomputing a metric series (leave-one-mailbox-out, null model) is done by a function passed in,
normally `enron_case.network.metrics.compute_series`; tests inject a fake.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import numpy as np
import polars as pl

from enron_case.config import Config
from enron_case.contracts.vocab import DEFAULT_VARIANT
from enron_case.errors import ContractViolation
from enron_case.finding import nullmodel, stats
from enron_case.finding.stats import FloatArray, InsufficientData

UP, DOWN = 1, -1
# Stream labels: every random use draws from its own generator derived from config.seed.
_ESTIMATE_STREAM = 1
_NULL_STREAM = 2


@dataclass(frozen=True)
class Hypothesis:
    id: str
    metric: str
    scope: str
    direction: int


HYPOTHESES: tuple[Hypothesis, ...] = (
    Hypothesis("H1", "indegree_gini", "core", UP),
    Hypothesis("H2", "cross_community_share", "observed", UP),
    Hypothesis("H3", "external_share", "observed", DOWN),
    Hypothesis("H4", "tie_turnover", "core", UP),
)


class Recompute(Protocol):
    def __call__(
        self,
        events: pl.DataFrame,
        entities_p: pl.DataFrame,
        communities: pl.DataFrame,
        config: Config,
        variant: str = DEFAULT_VARIANT,
        exclude_pids: frozenset[str] = frozenset(),
    ) -> pl.DataFrame: ...


@dataclass(frozen=True)
class Network:
    """The inputs a metric series is recomputed from."""

    events: pl.DataFrame
    entities_p: pl.DataFrame
    communities: pl.DataFrame


@dataclass(frozen=True)
class Series:
    weeks: list[date]
    values: FloatArray


@dataclass(frozen=True)
class Estimate:
    change_week: date
    p_perm: float
    effect: float
    ci_low: float
    ci_high: float


@dataclass(frozen=True)
class Evidence:
    """Everything `select` needs to decide one hypothesis. NaN marks an undefined number."""

    hypothesis: Hypothesis
    change_week: date | None
    p_perm: float
    effect: float
    ci_low: float
    ci_high: float
    null_z: float
    loo_effects: tuple[float, ...]
    variants_passed: int
    variants_total: int


def series_of(
    metric_series: pl.DataFrame, hypothesis: Hypothesis, variant: str, config: Config
) -> Series:
    """Defined weeks of one metric series inside the analysis window, in week order."""
    rows = metric_series.filter(
        (pl.col("metric") == hypothesis.metric)
        & (pl.col("scope") == hypothesis.scope)
        & (pl.col("variant") == variant)
        & pl.col("week").is_between(config.analysis_start, config.analysis_end)
    )
    if rows.height == 0:
        raise ContractViolation(
            f"metric_series has no rows for {hypothesis.id} ({hypothesis.metric}, "
            f"{hypothesis.scope}, {variant})"
        )
    rows = rows.filter(pl.col("value").is_not_null() & pl.col("value").is_not_nan()).sort("week")
    return Series(rows.get_column("week").to_list(), rows.get_column("value").to_numpy())


def _periods(series: Series, change_week: date, config: Config) -> tuple[FloatArray, FloatArray]:
    weeks = np.array(series.weeks, dtype="datetime64[D]")
    baseline = (weeks >= np.datetime64(config.baseline_start)) & (
        weeks <= np.datetime64(config.baseline_end)
    )
    after = weeks >= np.datetime64(change_week)
    return series.values[baseline], series.values[after]


def effect_at(series: Series, change_week: date, config: Config) -> float:
    """Standardised effect of the weeks from `change_week` on, against the baseline."""
    before, after = _periods(series, change_week, config)
    return stats.effect_size(before, after, min_baseline_weeks=config.min_baseline_weeks)


def bootstrap_ci(
    before: FloatArray, after: FloatArray, config: Config, rng: np.random.Generator
) -> tuple[float, float]:
    """`stats.block_bootstrap_ci` with the configured repetitions, block and level."""
    return stats.block_bootstrap_ci(
        before,
        after,
        config.bootstrap_reps,
        rng,
        block_weeks=config.block_weeks,
        ci_level=config.ci_level,
        min_baseline_weeks=config.min_baseline_weeks,
    )


def _first_candidate(series: Series, config: Config) -> int:
    """Index of the first week after the baseline: the change point is searched from there."""
    return sum(week <= config.baseline_end for week in series.weeks)


def searched_effect(series: Series, direction: int, config: Config) -> float:
    """Effect at the series' own most likely change week, found by the same search as the
    observed estimate. A null replicate needs that search too: the observed effect is the
    maximum over candidate weeks, so a null taken at one fixed week understates it."""
    index = stats.best_change_index(
        series.values,
        _first_candidate(series, config),
        direction,
        min_after_weeks=config.min_after_weeks,
    )
    return effect_at(series, series.weeks[index], config)


def estimate(series: Series, direction: int, config: Config, rng: np.random.Generator) -> Estimate:
    """Change point, its permutation p-value, the effect there and its bootstrap interval."""
    found = stats.change_point(
        series.values,
        _first_candidate(series, config),
        direction,
        config.permutations,
        rng,
        min_after_weeks=config.min_after_weeks,
    )
    change_week = series.weeks[found.index]
    before, after = _periods(series, change_week, config)
    low, high = bootstrap_ci(before, after, config, rng)
    effect = stats.effect_size(before, after, min_baseline_weeks=config.min_baseline_weeks)
    return Estimate(change_week, found.p_value, effect, low, high)


def _estimate_or_none(
    series: Series, hyp_index: int, variant_index: int, config: Config
) -> Estimate | None:
    """Estimate on its own generator (one per hypothesis and variant); None if undefined."""
    hyp = HYPOTHESES[hyp_index]
    rng = stats.rng_for(config.seed, _ESTIMATE_STREAM, hyp_index, variant_index)
    try:
        return estimate(series, hyp.direction, config, rng)
    except InsufficientData:
        return None


def _variant_passes(found: Estimate | None, direction: int, alpha: float) -> bool:
    if found is None:
        return False
    return found.p_perm < alpha and stats.on_side(direction, found.ci_low, found.ci_high)


# How a recomputed series yields an effect: at the observed change week (leave-one-out asks
# whether that change survives), or at its own searched week (a null replicate).
EffectOf = Callable[[Series, Hypothesis, Estimate, Config], float]


def _at_observed_week(series: Series, hyp: Hypothesis, found: Estimate, config: Config) -> float:
    return effect_at(series, found.change_week, config)


def _at_searched_week(series: Series, hyp: Hypothesis, found: Estimate, config: Config) -> float:
    return searched_effect(series, hyp.direction, config)


def _effects_or_nan(
    recomputed: pl.DataFrame,
    estimates: dict[str, Estimate | None],
    config: Config,
    effect_of: EffectOf,
) -> dict[str, float]:
    effects: dict[str, float] = {}
    for hyp in HYPOTHESES:
        found = estimates[hyp.id]
        if found is None:
            effects[hyp.id] = math.nan
            continue
        try:
            series = series_of(recomputed, hyp, DEFAULT_VARIANT, config)
            effects[hyp.id] = effect_of(series, hyp, found, config)
        except InsufficientData:
            effects[hyp.id] = math.nan
    return effects


def _collect(
    runs: Iterable[pl.DataFrame],
    estimates: dict[str, Estimate | None],
    config: Config,
    effect_of: EffectOf,
) -> dict[str, list[float]]:
    collected: dict[str, list[float]] = {hyp.id: [] for hyp in HYPOTHESES}
    for recomputed in runs:
        for hyp_id, value in _effects_or_nan(recomputed, estimates, config, effect_of).items():
            collected[hyp_id].append(value)
    return collected


def leave_one_out(
    recompute: Recompute,
    network: Network,
    estimates: dict[str, Estimate | None],
    config: Config,
) -> dict[str, list[float]]:
    """Effect at each hypothesis' change week with each custodian left out in turn."""
    custodians = sorted(
        network.entities_p.filter(pl.col("is_custodian")).get_column("pid").to_list()
    )
    runs = (
        recompute(
            network.events,
            network.entities_p,
            network.communities,
            config,
            exclude_pids=frozenset({pid}),
        )
        for pid in custodians
    )
    return _collect(runs, estimates, config, _at_observed_week)


def null_effects(
    recompute: Recompute,
    network: Network,
    estimates: dict[str, Estimate | None],
    config: Config,
) -> dict[str, list[float]]:
    """Effect on each of `config.null_replicates` rewired networks, each at its own searched
    change week, so the null faces the same search as the observed effect."""
    runs = (
        recompute(
            nullmodel.rewire(network.events, stats.rng_for(config.seed, _NULL_STREAM, replicate)),
            network.entities_p,
            network.communities,
            config,
        )
        for replicate in range(config.null_replicates)
    )
    return _collect(runs, estimates, config, _at_searched_week)


def _null_z(found: Estimate | None, null_values: list[float]) -> float:
    if found is None or any(math.isnan(x) for x in null_values):
        return math.nan
    return nullmodel.null_z(found.effect, null_values)


def _variants_passed(
    metric_series: pl.DataFrame, hyp_index: int, variants: list[str], config: Config
) -> int:
    hyp = HYPOTHESES[hyp_index]
    return sum(
        _variant_passes(
            _estimate_or_none(
                series_of(metric_series, hyp, variant, config), hyp_index, number, config
            ),
            hyp.direction,
            config.alpha,
        )
        for number, variant in enumerate(variants, start=1)
    )


def gather(
    metric_series: pl.DataFrame, network: Network, recompute: Recompute, config: Config
) -> list[Evidence]:
    """Evidence for H1–H4, in hypothesis order. An undefined estimate enters with p = 1."""
    estimates = {
        hyp.id: _estimate_or_none(
            series_of(metric_series, hyp, DEFAULT_VARIANT, config), index, 0, config
        )
        for index, hyp in enumerate(HYPOTHESES)
    }
    loo = leave_one_out(recompute, network, estimates, config)
    null = null_effects(recompute, network, estimates, config)
    variants = sorted(set(metric_series.get_column("variant").to_list()) - {DEFAULT_VARIANT})
    evidence = []
    for index, hyp in enumerate(HYPOTHESES):
        found = estimates[hyp.id]
        evidence.append(
            Evidence(
                hypothesis=hyp,
                change_week=found.change_week if found else None,
                p_perm=found.p_perm if found else 1.0,
                effect=found.effect if found else math.nan,
                ci_low=found.ci_low if found else math.nan,
                ci_high=found.ci_high if found else math.nan,
                null_z=_null_z(found, null[hyp.id]),
                loo_effects=tuple(loo[hyp.id]),
                variants_passed=_variants_passed(metric_series, index, variants, config)
                if found
                else 0,
                variants_total=len(variants),
            )
        )
    return evidence
