"""S8 release: write every published table through `kanon` (contracts: zone 3 · release)."""

from __future__ import annotations

import polars as pl

from enron_case.context import StageContext
from enron_case.release import kanon, tables, variants

PUBLISHED_SCOPE = "observed"


def run(ctx: StageContext) -> None:
    for name, df in published_tables(ctx).items():
        written = kanon.write(ctx, name, df)
        ctx.log(f"[release] {name}: {written.height} rows")


def published_tables(ctx: StageContext) -> dict[str, pl.DataFrame]:
    """Release R1: the aggregate tables plus quality, header, finding and risk tables."""
    ingest = ctx.read_counts("ingest_counts")
    edges = ctx.read("snapshots").filter(pl.col("scope") == PUBLISHED_SCOPE).drop("scope")
    r1 = variants.build_r1(
        edges, ctx.read("metric_series"), ctx.read("communities"), ctx.config.k_min
    )
    return {
        "data_quality": tables.data_quality(
            ingest, ctx.read_counts("clean_counts"), ctx.read_counts("identity_counts")
        ),
        "header_fields": tables.header_fields(ingest),
        "hypotheses": ctx.read("hypothesis_results"),
        "risk": ctx.read("risk_results"),
        **r1,
    }
