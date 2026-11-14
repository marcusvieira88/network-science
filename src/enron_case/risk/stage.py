"""S7 risk: attack our own output, measure uniqueness and the utility cost of each release.

Writes `risk_results`: one row per (release variant, attacker). The attack functions receive a
release and the attacker's auxiliary knowledge only; truth enters through `risk/score.py`,
which returns counts and rates.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl

from enron_case.config import Config
from enron_case.context import StageContext
from enron_case.contracts import vocab as v
from enron_case.finding import stats
from enron_case.release import variants
from enron_case.risk import aux_public, score, uniqueness, utility
from enron_case.risk.attack import Release, attack_a1, attack_a2, node_edges, person_edges
from enron_case.risk.features import NODE, node_features

BuildR0 = Callable[[pl.DataFrame], pl.DataFrame]
BuildAggregate = Callable[[pl.DataFrame, pl.DataFrame], dict[str, pl.DataFrame]]


@dataclass(frozen=True)
class Dependencies:
    """Interfaces owned by other work packages (WP-F, WP-H), injectable for tests. `pid_of`
    is None in a real run: the scorer then builds the keyed pseudonym function itself."""

    build_r0: BuildR0
    build_r1: BuildAggregate
    build_r2: BuildAggregate
    effect_size: utility.EffectFn
    pid_of: score.PidOf | None


def run(ctx: StageContext) -> None:
    run_with(ctx, real_dependencies(ctx.read("communities"), ctx.config))


def real_dependencies(communities: pl.DataFrame, config: Config) -> Dependencies:
    """Bind the other packages' public interfaces (release.variants, finding.stats)
    to the shapes this stage calls. R0 is the observed-scope snapshots; R1/R2 are built from
    those edges plus the baseline communities, exactly as the release stage builds what it
    publishes."""

    def build_r1(edges: pl.DataFrame, metric_series: pl.DataFrame) -> dict[str, pl.DataFrame]:
        return variants.build_r1(edges, metric_series, communities, config)

    def build_r2(edges: pl.DataFrame, metric_series: pl.DataFrame) -> dict[str, pl.DataFrame]:
        return variants.build_r2(edges, metric_series, communities, config)

    def effect_size(before: np.ndarray, after: np.ndarray) -> float:
        return stats.effect_size(before, after, min_baseline_weeks=config.min_baseline_weeks)

    return Dependencies(
        build_r0=variants.build_r0,
        build_r1=build_r1,
        build_r2=build_r2,
        effect_size=effect_size,
        pid_of=None,
    )


def run_with(ctx: StageContext, deps: Dependencies) -> None:
    entities_p = ctx.read("entities_p")
    metric_series = ctx.read("metric_series")
    r0 = deps.build_r0(ctx.read("snapshots"))
    releases: dict[str, Release] = {
        "R0": r0,
        "R1": deps.build_r1(r0, metric_series),
        "R2": deps.build_r2(r0, metric_series),
    }
    aux_edges = aux_public.load_aux_edges(ctx)
    scorer = score.Scorer.from_context(ctx, deps.pid_of)
    targets = node_level_persons(r0)
    custodians = set(entities_p.filter(pl.col("is_custodian")).get_column("pid")) & targets
    seeds = scorer.seeds(custodians, ctx.config.a2_seeds)
    effects = variant_effects(ctx, releases, metric_series, deps.effect_size)

    rows: list[dict[str, Any]] = []
    for name, release in releases.items():
        exposure = measure_uniqueness(release)
        gain = utility.compare(effects["restricted"], effects[name])
        if person_edges(release) is None:
            ctx.log(f"[risk] {name}: no person-level records; attackers have nothing to match")
        for attacker in v.ATTACKERS:
            if attacker == "A1":
                guesses = attack_a1(release, aux_edges, ctx.config.distance_chunk_rows)
                scored = targets
            else:
                guesses = attack_a2(release, aux_edges, seeds, ctx.config.a2_min_support)
                scored = targets - set(seeds)
            result = scorer.score(guesses, scored)
            ctx.log(
                f"[risk] {name}/{attacker}: {result.n_correct} of {result.n_targets} re-identified"
            )
            rows.append(
                {
                    "release_variant": name,
                    "attacker": attacker,
                    "n_targets": result.n_targets,
                    "unique_share": exposure.unique_share,
                    "median_anonymity_set": exposure.median_anonymity_set,
                    "reid_top1": result.rate,
                    "reid_ci_low": result.ci_low,
                    "reid_ci_high": result.ci_high,
                    "utility_effect_ratio": gain.effect_ratio,
                    "finding_survives": gain.finding_survives,
                }
            )
    ctx.write("risk_results", pl.DataFrame(rows))


def node_level_persons(r0: pl.DataFrame) -> set[str]:
    """Persons in scope: every pseudonym in the node-level release."""
    return set(node_features(node_edges(r0)).get_column(NODE))


def measure_uniqueness(release: Release) -> uniqueness.Uniqueness:
    if isinstance(release, dict):
        return uniqueness.summarize(uniqueness.aggregate_set_sizes(release))
    features = node_features(node_edges(release))
    return uniqueness.summarize(uniqueness.anonymity_set_sizes(features, NODE))


def variant_effects(
    ctx: StageContext,
    releases: dict[str, Release],
    metric_series: pl.DataFrame,
    effect_size: utility.EffectFn,
) -> dict[str, utility.Effect | None]:
    """Headline effect on the restricted data and on what each variant exposes. A node-level
    release exposes the full graph the metrics were computed from, so it reproduces them; an
    aggregate release exposes its published `weekly_metrics` only."""
    headline = utility.find_headline(ctx.read("hypothesis_results"))
    if headline is None:
        ctx.log("[risk] no headline finding; utility not applicable")
        return dict.fromkeys(["restricted", *releases])

    def effect_of(series: pl.DataFrame | None) -> utility.Effect | None:
        if series is None:
            return None
        before, after = utility.split_series(series, headline, ctx.config)
        return utility.effect_with_interval(
            before, after, effect_size, ctx.config.bootstrap_reps, ctx.config.seed
        )

    out: dict[str, utility.Effect | None] = {"restricted": effect_of(metric_series)}
    for name, release in releases.items():
        series = (
            metric_series if isinstance(release, pl.DataFrame) else release.get("weekly_metrics")
        )
        out[name] = effect_of(series)
        if out[name] is None:
            ctx.log(f"[risk] {name}: headline effect not computable from this release")
    return out
