"""S8 release: write every published table through `kanon` (contracts: zone 3 · release)."""

from __future__ import annotations

import polars as pl

from enron_case.context import StageContext
from enron_case.release import kanon, tables, variants


def run(ctx: StageContext) -> None:
    for name, df in published_tables(ctx).items():
        written = kanon.write(ctx, name, df)
        ctx.log(f"[release] {name}: {written.height} rows")


def published_tables(ctx: StageContext) -> dict[str, pl.DataFrame]:
    """Release R1: the aggregate tables plus quality, header, finding and risk tables."""
    ingest = ctx.read_counts("ingest_counts")
    edges = variants.build_r0(ctx.read("snapshots"))
    r1 = variants.build_r1(
        edges, ctx.read("metric_series"), ctx.read("communities"), ctx.config.k_min
    )
    return {
        "data_quality": tables.data_quality(
            ingest,
            ctx.read_counts("clean_counts"),
            ctx.read_counts("identity_counts"),
            ctx.read_counts("identity_manual"),
        ),
        "header_fields": tables.header_fields(ingest),
        "hypotheses": ctx.read("hypothesis_results"),
        "risk": ctx.read("risk_results"),
        "artifact_checks": tables.artifact_checks(ctx.read("artifact_results"), ctx.config.k_min),
        **r1,
    }
