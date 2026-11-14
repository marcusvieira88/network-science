"""S5 network stage: snapshots, baseline communities and metric series."""

from __future__ import annotations

import polars as pl

from enron_case.context import StageContext
from enron_case.contracts.vocab import DEFAULT_VARIANT
from enron_case.network.communities import UNASSIGNED, baseline_communities
from enron_case.network.metrics import compute_series
from enron_case.network.snapshots import build_snapshots


def run(ctx: StageContext) -> None:
    events, entities_p = ctx.read("events"), ctx.read("entities_p")
    snapshots = ctx.write("snapshots", build_snapshots(events, entities_p, ctx.config))
    communities = ctx.write("communities", baseline_communities(events, entities_p, ctx.config))
    variants = (DEFAULT_VARIANT, *ctx.config.sensitivity_variants)
    series = ctx.write(
        "metric_series",
        pl.concat(
            [
                compute_series(events, entities_p, communities, ctx.config, variant)
                for variant in variants
            ]
        ),
    )
    assigned = communities.filter(pl.col("community") != UNASSIGNED)
    ctx.log(
        f"network: {snapshots.height} snapshot ties, "
        f"{assigned.get_column('community').n_unique()} communities over "
        f"{assigned.height} persons, {series.height} metric rows in {len(variants)} variants"
    )
