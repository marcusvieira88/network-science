"""Attacker-observable node features, computed the same way on both sides of an attack.

The input is a weekly edge list `(week, src, dst)` whose node labels are either addresses (the
attacker's own view of the public archive) or pseudonyms (a node-level release). Nothing here
knows which, so the attacker's features and the release's features are comparable by
construction.
"""

from __future__ import annotations

from datetime import date

import polars as pl

WEEK = "week"
SRC = "src"
DST = "dst"
NODE = "node"
N_OUT = "n_out"
N_IN = "n_in"
DEGREE = "degree"
FIRST_WEEK = "first_week"
LAST_WEEK = "last_week"
ACTIVITY = "activity"
EDGE_SCHEMA: dict[str, pl.DataType] = {WEEK: pl.Date(), SRC: pl.String(), DST: pl.String()}


def clean_edges(edges: pl.DataFrame) -> pl.DataFrame:
    """Distinct weekly directed ties without self-loops."""
    return (
        edges.select(WEEK, SRC, DST)
        .filter(pl.col(SRC) != pl.col(DST))
        .unique()
        .sort(WEEK, SRC, DST)
    )


def weekly_activity(edges: pl.DataFrame) -> pl.DataFrame:
    """Per node and week: distinct persons written to (`n_out`) and heard from (`n_in`)."""
    ties = clean_edges(edges)
    sent = ties.group_by(SRC, WEEK).agg(pl.col(DST).n_unique().alias(N_OUT)).rename({SRC: NODE})
    received = ties.group_by(DST, WEEK).agg(pl.col(SRC).n_unique().alias(N_IN)).rename({DST: NODE})
    return (
        sent.join(received, on=[NODE, WEEK], how="full", coalesce=True)
        .with_columns(
            pl.col(N_OUT).fill_null(0).cast(pl.Int64), pl.col(N_IN).fill_null(0).cast(pl.Int64)
        )
        .sort(NODE, WEEK)
    )


def node_features(edges: pl.DataFrame) -> pl.DataFrame:
    """Per node: degree (distinct neighbours either way), first and last active week, and the
    weekly activity vector rendered as one comparable string."""
    ties = clean_edges(edges)
    undirected = pl.concat(
        [
            ties.select(pl.col(SRC).alias(NODE), pl.col(DST).alias("other")),
            ties.select(pl.col(DST).alias(NODE), pl.col(SRC).alias("other")),
        ]
    )
    degree = undirected.group_by(NODE).agg(pl.col("other").n_unique().cast(pl.Int64).alias(DEGREE))
    activity = (
        weekly_activity(ties)
        .group_by(NODE)
        .agg(
            pl.col(WEEK).min().alias(FIRST_WEEK),
            pl.col(WEEK).max().alias(LAST_WEEK),
            pl.format("{}:{}:{}", WEEK, N_OUT, N_IN).sort().str.join("|").alias(ACTIVITY),
        )
    )
    return degree.join(activity, on=NODE).sort(NODE)


def weekly_contacts(edges: pl.DataFrame) -> dict[str, set[tuple[date, str]]]:
    """Per node, every (week, counterpart) it exchanged mail with, either direction."""
    out: dict[str, set[tuple[date, str]]] = {}
    for week, src, dst in clean_edges(edges).iter_rows():
        out.setdefault(src, set()).add((week, dst))
        out.setdefault(dst, set()).add((week, src))
    return out
