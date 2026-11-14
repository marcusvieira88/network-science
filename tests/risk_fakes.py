"""Stand-ins for interfaces other work packages own (WP-D, WP-F, WP-H), for risk tests only.

They follow the briefs' signatures and semantics closely enough to drive the risk stage; they
are not reference implementations. R0 is the real `release.variants.build_r0`: it only selects
the published snapshot edges.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from enron_case.release import variants
from enron_case.risk.stage import Dependencies
from enron_case.synth.fixtures import fixture_pid


def build_r1(edges: pl.DataFrame, metric_series: pl.DataFrame) -> dict[str, pl.DataFrame]:
    """Aggregates only: weekly metrics and a degree distribution with persons per cell."""
    degree = pl.DataFrame(
        {"period": ["2000H1"] * 3, "degree_bucket": ["1", "2-4", "5-9"], "persons": [6, 12, None]}
    )
    return {"weekly_metrics": metric_series, "degree_distribution": degree}


def build_r2(
    edges: pl.DataFrame, metric_series: pl.DataFrame, seed: int
) -> dict[str, pl.DataFrame]:
    tables = build_r1(edges, metric_series)
    rng = np.random.default_rng(seed)
    noise = rng.laplace(0.0, 0.01, metric_series.height)
    tables["weekly_metrics"] = metric_series.with_columns(pl.col("value") + noise)
    return tables


def effect_size(before: np.ndarray, after: np.ndarray) -> float:
    return float((np.mean(after) - np.mean(before)) / np.std(before, ddof=1))


def fixture_dependencies() -> Dependencies:
    """Fakes plus the fixture's own pseudonym function (the fixtures use their own key)."""
    return Dependencies(
        build_r0=variants.build_r0,
        build_r1=build_r1,
        build_r2=build_r2,
        effect_size=effect_size,
        pid_of=fixture_pid,
    )
