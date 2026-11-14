"""Release variants attacked by the risk stage (research R12) and published by this stage.

R0: node-level weekly person edges. Personal data; held in memory, never written to release.
R1: the aggregate release tables, k-thresholded through `kanon`.
R2: R1 with seeded Laplace noise on counts and weights.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from enron_case.release import kanon, mitigate

PERSON_TYPE = "person"
R0_SORT = ("week", "src_pid", "dst_pid")


def build_r0(events: pl.DataFrame, entities_p: pl.DataFrame) -> pl.DataFrame:
    """Weekly edges between internal persons from in-network events: week, src_pid, dst_pid,
    weight (sum of event weights), n_messages (distinct messages)."""
    persons = entities_p.filter((pl.col("type") == PERSON_TYPE) & pl.col("is_internal"))
    person_pids = persons.get_column("pid")
    return (
        events.filter(
            pl.col("in_network")
            & pl.col("sender_pid").is_in(person_pids.implode())
            & pl.col("recipient_pid").is_in(person_pids.implode())
        )
        .with_columns(pl.col("ts_hour").dt.date().dt.truncate("1w").alias("week"))
        .group_by("week", "sender_pid", "recipient_pid")
        .agg(
            pl.col("weight").sum(),
            pl.col("msg_pid").n_unique().cast(pl.Int64).alias("n_messages"),
        )
        .select(
            "week",
            pl.col("sender_pid").alias("src_pid"),
            pl.col("recipient_pid").alias("dst_pid"),
            "weight",
            "n_messages",
        )
        .sort(R0_SORT)
    )


def build_r1(
    edges: pl.DataFrame, metric_series: pl.DataFrame, communities: pl.DataFrame, k_min: int
) -> dict[str, pl.DataFrame]:
    """The network-derived release tables. `edges` has the R0 columns."""
    groups = group_sizes(communities, k_min)
    tables = {
        "weekly_metrics": weekly_metrics(metric_series, k_min),
        "degree_distribution": degree_distribution(edges, k_min),
        "community_graph": community_graph(edges, communities, groups, k_min),
        "community_groups": groups,
    }
    return {name: kanon.enforce(name, df, k_min) for name, df in tables.items()}


def build_r2(
    edges: pl.DataFrame,
    metric_series: pl.DataFrame,
    communities: pl.DataFrame,
    k_min: int,
    seed: int,
) -> dict[str, pl.DataFrame]:
    """R1 with seeded Laplace noise on degree counts and on group tie weights and messages.
    Cells whose noisy count falls below k are suppressed again."""
    rng = np.random.default_rng(seed)
    r1 = build_r1(edges, metric_series, communities, k_min)
    scale = mitigate.R2_NOISE_SCALE
    degree = r1["degree_distribution"]
    degree = degree.with_columns(mitigate.add_laplace(degree.get_column("persons"), scale, rng))
    degree = kanon.complementary_suppress(
        kanon.suppress_below(degree, "persons", k_min), "persons", "period"
    )
    graph = r1["community_graph"]
    graph = graph.with_columns(
        mitigate.add_laplace(graph.get_column("weight"), scale, rng),
        mitigate.add_laplace(graph.get_column("n_messages"), scale, rng),
    )
    noisy = {**r1, "degree_distribution": degree, "community_graph": graph}
    return {name: kanon.enforce(name, df, k_min) for name, df in noisy.items()}


def weekly_metrics(metric_series: pl.DataFrame, k: int) -> pl.DataFrame:
    return kanon.suppress_below(metric_series, "n_active", k, dependents=("value",))


def degree_distribution(edges: pl.DataFrame, k: int) -> pl.DataFrame:
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
        .group_by("period", mitigate.degree_bucket(pl.col("degree")).alias("degree_bucket"))
        .agg(pl.len().cast(pl.Int64).alias("persons"))
    )
    grid = (
        persons.select("period")
        .unique()
        .join(pl.DataFrame({"degree_bucket": mitigate.bucket_labels()}), how="cross")
    )
    full = grid.join(persons, on=["period", "degree_bucket"], how="left").with_columns(
        pl.col("persons").fill_null(0)
    )
    full = full.sort("period", "degree_bucket")
    return kanon.complementary_suppress(
        kanon.suppress_below(full, "persons", k), "persons", "period"
    )


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
            pl.col("weight").sum(),
            pl.col("n_messages").sum(),
            pl.col("src_pid").n_unique().alias("senders"),
        )
    )
    return kanon.drop_below(ties, "senders", k).drop("senders")
