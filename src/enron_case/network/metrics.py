"""The eight metric series per scope, period and variant (docs/metrics.md, "Metrics")."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from enron_case.config import Config
from enron_case.contracts import schemas
from enron_case.contracts import vocab as v
from enron_case.contracts.vocab import DEFAULT_VARIANT
from enron_case.errors import UsageError
from enron_case.network.communities import UNASSIGNED
from enron_case.network.snapshots import (
    CORE_SCOPE,
    MONTH,
    aggregate_ties,
    period_interval,
    period_start,
    person_network,
    sender_view,
    stable_sum,
    with_period,
)

CAP_PREFIX = "cap="
MONTH_VARIANT = "window=month"
PAIR = ("week", "sender_pid", "recipient_pid")


@dataclass(frozen=True)
class Variant:
    window: str
    recipient_cap: int | None


def parse_variant(label: str, config: Config) -> Variant:
    """Translate a variant label (`default`, `cap=N`, `window=month`) into its settings."""
    if label == DEFAULT_VARIANT:
        return Variant(config.window, None)
    if label == MONTH_VARIANT:
        return Variant(MONTH, None)
    if label.startswith(CAP_PREFIX):
        try:
            return Variant(config.window, int(label.removeprefix(CAP_PREFIX)))
        except ValueError as exc:
            raise UsageError(f"bad recipient cap in variant: {label}") from exc
    raise UsageError(f"unknown variant: {label}")


def periods(config: Config, window: str) -> pl.DataFrame:
    """Every period start in the analysis window, in order."""
    start = period_start(config.analysis_start, window)
    weeks = pl.date_range(start, config.analysis_end, period_interval(window), eager=True)
    return pl.DataFrame({"week": weeks})


def restrict(events: pl.DataFrame, variant: Variant, exclude_pids: frozenset[str]) -> pl.DataFrame:
    """Apply the recipient cap and drop every event touching an excluded person."""
    if variant.recipient_cap is not None:
        events = events.filter(pl.col("n_recipients") <= variant.recipient_cap)
    if exclude_pids:
        excluded = list(exclude_pids)
        events = events.filter(
            ~pl.col("sender_pid").is_in(excluded), ~pl.col("recipient_pid").is_in(excluded)
        )
    return events


def volume_by_period(network: pl.DataFrame) -> pl.DataFrame:
    return network.group_by("week").agg(pl.col("msg_pid").n_unique().alias("volume"))


def node_stats(ties: pl.DataFrame) -> pl.DataFrame:
    """Active persons and the Gini of weighted in-degree over them, per period."""
    nodes = pl.concat(
        [
            ties.select("week", pl.col("sender_pid").alias("pid")),
            ties.select("week", pl.col("recipient_pid").alias("pid")),
        ]
    ).unique()
    indegree = ties.group_by("week", pl.col("recipient_pid").alias("pid")).agg(
        stable_sum(pl.col("weight")).alias("indegree")
    )
    ranked = (
        nodes.join(indegree, on=["week", "pid"], how="left")
        .with_columns(pl.col("indegree").fill_null(0.0))
        .sort("week", "indegree")
        .with_columns(pl.int_range(1, pl.len() + 1).over("week").alias("rank"))
    )
    n, total = pl.col("n_active"), pl.col("total")
    return (
        ranked.group_by("week")
        .agg(
            pl.len().cast(pl.Int64).alias("n_active"),
            stable_sum(pl.col("indegree")).alias("total"),
            stable_sum(pl.col("rank") * pl.col("indegree")).alias("rank_weighted"),
        )
        .with_columns(
            pl.when(total > 0)
            .then(2 * pl.col("rank_weighted") / (n * total) - (n + 1) / n)
            .alias("indegree_gini")
        )
        .select("week", "n_active", "indegree_gini")
    )


def tie_stats(ties: pl.DataFrame, communities: pl.DataFrame) -> pl.DataFrame:
    """Tie count, reciprocated ties and community-crossing weight, per period."""
    reverse = ties.select(
        "week",
        pl.col("recipient_pid").alias("sender_pid"),
        pl.col("sender_pid").alias("recipient_pid"),
    )
    community = communities.select("pid", "community")
    labelled = (
        ties.join(reverse.with_columns(pl.lit(True).alias("reciprocated")), on=PAIR, how="left")
        .join(community.rename({"pid": "sender_pid", "community": "src_c"}), "sender_pid", "left")
        .join(
            community.rename({"pid": "recipient_pid", "community": "dst_c"}),
            "recipient_pid",
            "left",
        )
        .with_columns(pl.col("src_c", "dst_c").fill_null(UNASSIGNED))
    )
    assigned = (pl.col("src_c") != UNASSIGNED) & (pl.col("dst_c") != UNASSIGNED)
    crossing = assigned & (pl.col("src_c") != pl.col("dst_c"))
    return labelled.group_by("week").agg(
        pl.len().cast(pl.Int64).alias("n_ties"),
        pl.col("reciprocated").fill_null(False).sum().cast(pl.Int64).alias("n_reciprocated"),
        stable_sum(pl.col("weight").filter(assigned)).alias("assigned_weight"),
        stable_sum(pl.col("weight").filter(crossing)).alias("crossing_weight"),
    )


def shared_ties(ties: pl.DataFrame, calendar: pl.DataFrame) -> pl.DataFrame:
    """Ties present in a period and in the period before it."""
    following = calendar.select(
        pl.col("week").alias("previous"), pl.col("week").shift(-1).alias("next")
    ).drop_nulls()
    moved_forward = (
        ties.select(PAIR)
        .join(following, left_on="week", right_on="previous")
        .select(pl.col("next").alias("week"), *PAIR[1:])
    )
    return (
        ties.join(moved_forward, on=PAIR, how="semi")
        .group_by("week")
        .agg(pl.len().cast(pl.Int64).alias("n_shared"))
    )


def external_stats(view: pl.DataFrame, scope: str) -> pl.DataFrame:
    """Weight sent by the scope's senders to all persons and to external persons."""
    senders = view.filter(pl.col("sender_custodian")) if scope == CORE_SCOPE else view
    return senders.group_by("week").agg(
        stable_sum(pl.col("weight")).alias("sent_weight"),
        stable_sum(pl.col("weight").filter(~pl.col("recipient_internal"))).alias("external_weight"),
    )


def metric_columns(k_min: int) -> list[pl.Expr]:
    """The eight metrics from the per-period statistics; null where undefined."""
    n = pl.col("n_active")
    n_ties = pl.col("n_ties")
    defined = n >= k_min
    previous_defined = defined.shift(1).fill_null(False)
    union = n_ties + n_ties.shift(1) - pl.col("n_shared")
    values = {
        "volume": pl.col("volume").cast(pl.Float64),
        "active_persons": n.cast(pl.Float64),
        "density": pl.when(n > 1).then(n_ties / (n * (n - 1))),
        "reciprocity": pl.when(n_ties > 0).then(pl.col("n_reciprocated") / n_ties),
        "indegree_gini": pl.col("indegree_gini"),
        "cross_community_share": pl.when(pl.col("assigned_weight") > 0).then(
            pl.col("crossing_weight") / pl.col("assigned_weight")
        ),
        "external_share": pl.when(pl.col("sent_weight") > 0).then(
            pl.col("external_weight") / pl.col("sent_weight")
        ),
        "tie_turnover": pl.when(previous_defined & (union > 0)).then(
            1 - pl.col("n_shared") / union
        ),
    }
    assert tuple(values) == v.METRICS
    return [pl.when(defined).then(expr).alias(name) for name, expr in values.items()]


def scope_series(
    view: pl.DataFrame,
    scope: str,
    communities: pl.DataFrame,
    calendar: pl.DataFrame,
    k_min: int,
) -> pl.DataFrame:
    """Long rows (week, metric, value, n_active) for one scope."""
    network = person_network(view, scope)
    ties = aggregate_ties(network)
    stats = calendar
    for part in (
        volume_by_period(network),
        node_stats(ties),
        tie_stats(ties, communities),
        shared_ties(ties, calendar),
        external_stats(view, scope),
    ):
        stats = stats.join(part, on="week", how="left")
    counts = ("volume", "n_active", "n_ties", "n_reciprocated", "n_shared")
    stats = stats.sort("week").with_columns(pl.col(counts).fill_null(0).cast(pl.Int64))
    return stats.select("week", "n_active", *metric_columns(k_min)).unpivot(
        index=["week", "n_active"], variable_name="metric", value_name="value"
    )


def compute_series(
    events: pl.DataFrame,
    entities_p: pl.DataFrame,
    communities: pl.DataFrame,
    config: Config,
    variant: str = DEFAULT_VARIANT,
    exclude_pids: frozenset[str] = frozenset(),
) -> pl.DataFrame:
    """Rows of `metric_series` for both scopes under one variant (public interface for WP-F)."""
    settings = parse_variant(variant, config)
    kept = restrict(events, settings, exclude_pids)
    view = with_period(sender_view(kept, entities_p), config, settings.window)
    calendar = periods(config, settings.window)
    frames = [
        scope_series(view, scope, communities, calendar, config.k_min).with_columns(
            pl.lit(scope).alias("scope"), pl.lit(variant).alias("variant")
        )
        for scope in v.SCOPES
    ]
    return schemas.conform(pl.concat(frames), "metric_series")
