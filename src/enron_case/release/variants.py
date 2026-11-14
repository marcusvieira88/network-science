"""Release variants attacked by the risk stage (research R12) and published by this stage.

R0: node-level weekly person edges (observed-scope snapshots). Personal data; held in memory,
    never written to release.
R1: the aggregate release tables, k-thresholded through `kanon`.
R2: R1 with seeded Laplace noise on counts and weights.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from enron_case.config import Config
from enron_case.contracts.vocab import DEFAULT_VARIANT, OBSERVED_SCOPE
from enron_case.network.snapshots import stable_sum
from enron_case.release import kanon, mitigate

# The scope the release publishes and the risk stage attacks: every internal person.
PUBLISHED_SCOPE = OBSERVED_SCOPE


def build_r0(snapshots: pl.DataFrame) -> pl.DataFrame:
    """The node-level weekly person edges every release is built from: the observed-scope
    `snapshots` (analysis window only), without the scope column."""
    return snapshots.filter(pl.col("scope") == PUBLISHED_SCOPE).drop("scope")


def build_r1(
    edges: pl.DataFrame, metric_series: pl.DataFrame, communities: pl.DataFrame, config: Config
) -> dict[str, pl.DataFrame]:
    """The network-derived release tables. `edges` has the R0 columns."""
    k_min = config.k_min
    groups = group_sizes(communities, k_min)
    tables = {
        "weekly_metrics": weekly_metrics(metric_series, k_min),
        "degree_distribution": degree_distribution(edges, k_min, config.degree_bucket_floors),
        "community_graph": community_graph(edges, communities, groups, k_min),
        "community_groups": groups,
    }
    return {name: kanon.enforce(name, df, k_min) for name, df in tables.items()}


def build_r2(
    edges: pl.DataFrame,
    metric_series: pl.DataFrame,
    communities: pl.DataFrame,
    config: Config,
) -> dict[str, pl.DataFrame]:
    """R1 with seeded Laplace noise on degree counts and on group tie weights and messages.
    Cells whose noisy count falls below k are suppressed again."""
    k_min = config.k_min
    rng = np.random.default_rng(config.seed)
    r1 = build_r1(edges, metric_series, communities, config)
    scale = config.r2_noise_scale
    degree = r1["degree_distribution"]
    degree = degree.with_columns(mitigate.add_laplace(degree.get_column("persons"), scale, rng))
    degree = kanon.suppress_partition(degree, "persons", "period", k_min)
    graph = r1["community_graph"]
    graph = graph.with_columns(
        mitigate.add_laplace(graph.get_column("weight"), scale, rng),
        mitigate.add_laplace(graph.get_column("n_messages"), scale, rng),
    )
    noisy = {**r1, "degree_distribution": degree, "community_graph": graph}
    return {name: kanon.enforce(name, df, k_min) for name, df in noisy.items()}


def weekly_metrics(metric_series: pl.DataFrame, k: int) -> pl.DataFrame:
    """The default series only: a sensitivity variant published next to it would let default
    minus variant `n_active` reveal groups smaller than k. Variants stay restricted and feed the
    finding's robustness check."""
    default = metric_series.filter(pl.col("variant") == DEFAULT_VARIANT)
    return kanon.suppress_below(default, "n_active", k, dependents=("value",))


def degree_distribution(edges: pl.DataFrame, k: int, floors: tuple[int, ...]) -> pl.DataFrame:
    """Persons per (half-year, degree bucket); degree = distinct contacts, either direction."""
    undirected = pl.concat(
        [
            edges.select("week", pl.col("src_pid").alias("a"), pl.col("dst_pid").alias("b")),
            edges.select("week", pl.col("dst_pid").alias("a"), pl.col("src_pid").alias("b")),
        ]
    ).filter(pl.col("a") != pl.col("b"))
    persons = (
        undirected.group_by(mitigate.half_year(pl.col("week")).alias("period"), "a")
        .agg(pl.col("b").n_unique().alias("degree"))
        .group_by("period", mitigate.degree_bucket(pl.col("degree"), floors).alias("degree_bucket"))
        .agg(pl.len().cast(pl.Int64).alias("persons"))
    )
    grid = (
        persons.select("period")
        .unique()
        .join(pl.DataFrame({"degree_bucket": mitigate.bucket_labels(floors)}), how="cross")
    )
    full = grid.join(persons, on=["period", "degree_bucket"], how="left").with_columns(
        pl.col("persons").fill_null(0)
    )
    full = full.sort("period", "degree_bucket")
    return kanon.suppress_partition(full, "persons", "period", k)


def group_sizes(communities: pl.DataFrame, k: int) -> pl.DataFrame:
    """Published groups and their sizes; an `other` group below k is not published."""
    sizes = (
        mitigate.group_labels(communities, k)
        .group_by("group")
        .agg(pl.len().cast(pl.Int64).alias("n_persons"))
        .sort("group")
    )
    return kanon.drop_below(sizes, "n_persons", k)


def community_graph(
    edges: pl.DataFrame, communities: pl.DataFrame, groups: pl.DataFrame, k: int
) -> pl.DataFrame:
    """Weekly group-to-group ties between published groups with at least k distinct senders."""
    labels = mitigate.group_labels(communities, k).filter(
        pl.col("group").is_in(groups.get_column("group").implode())
    )
    ties = (
        edges.join(labels.rename({"pid": "src_pid", "group": "src_group"}), on="src_pid")
        .join(labels.rename({"pid": "dst_pid", "group": "dst_group"}), on="dst_pid")
        .group_by("week", "src_group", "dst_group")
        .agg(
            stable_sum(pl.col("weight")),
            pl.col("n_messages").sum(),
            pl.col("src_pid").n_unique().alias("senders"),
        )
    )
    return kanon.drop_below(ties, "senders", k).drop("senders")
