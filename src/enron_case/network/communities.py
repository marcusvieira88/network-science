"""Baseline communities, frozen on the baseline period (docs/metrics.md, "communities")."""

from __future__ import annotations

import networkx as nx
import polars as pl

from enron_case.config import Config
from enron_case.network.snapshots import (
    OBSERVED_SCOPE,
    PERSON,
    between,
    person_network,
    sender_view,
    stable_sum,
)

UNASSIGNED = -1


def baseline_graph(events: pl.DataFrame, entities_p: pl.DataFrame, config: Config) -> nx.Graph:
    """Undirected weighted observed network of the baseline period, built in sorted order."""
    view = between(sender_view(events, entities_p), config.baseline_start, config.baseline_end)
    ties = person_network(view, OBSERVED_SCOPE).select(
        pl.min_horizontal("sender_pid", "recipient_pid").alias("u"),
        pl.max_horizontal("sender_pid", "recipient_pid").alias("v"),
        "weight",
    )
    edges = ties.group_by("u", "v").agg(stable_sum(pl.col("weight"))).sort("u", "v")
    graph = nx.Graph()
    graph.add_nodes_from(sorted(set(edges.get_column("u")) | set(edges.get_column("v"))))
    graph.add_weighted_edges_from(edges.iter_rows())
    return graph


def numbered(groups: list[set[str]]) -> dict[str, int]:
    """Number communities by decreasing size, ties broken by their smallest pid."""
    ordered = sorted(groups, key=lambda group: (-len(group), min(group)))
    return {pid: number for number, group in enumerate(ordered) for pid in group}


def baseline_communities(
    events: pl.DataFrame, entities_p: pl.DataFrame, config: Config
) -> pl.DataFrame:
    """Rows of the `communities` table: every internal person, -1 if not in the baseline."""
    graph = baseline_graph(events, entities_p, config)
    groups = nx.community.louvain_communities(graph, weight="weight", seed=config.seed)
    labels = numbered([set(group) for group in groups])
    persons = entities_p.filter(pl.col("type") == PERSON, pl.col("is_internal"))
    return persons.select(
        "pid",
        pl.col("pid")
        .replace_strict(labels, default=UNASSIGNED, return_dtype=pl.Int64)
        .alias("community"),
    ).sort("pid")
