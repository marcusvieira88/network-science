"""Release mitigations: time coarsening, degree bucketing, group re-keying and noise.

Pure functions over polars data. Minimum group size itself is enforced in `kanon`.
"""

from __future__ import annotations

import numpy as np
import polars as pl

# Weighted-degree buckets published per half-year: (label, lowest degree in the bucket).
DEGREE_BUCKETS: tuple[tuple[str, int], ...] = (("1", 1), ("2-4", 2), ("5-9", 5), ("10+", 10))
LAST_MONTH_OF_FIRST_HALF = 6
GROUP_PREFIX = "G"
OTHER_GROUP = "other"
UNASSIGNED_COMMUNITY = -1
# Scale of the Laplace noise added to counts and weights in release R2 (a sketch, not a
# calibrated privacy budget; research R12).
R2_NOISE_SCALE = 1.0


def half_year(week: pl.Expr) -> pl.Expr:
    """`2000H1` / `2000H2` label of the half-year a week's Monday falls in."""
    half = pl.when(week.dt.month() <= LAST_MONTH_OF_FIRST_HALF).then(1).otherwise(2)
    return pl.format("{}H{}", week.dt.year(), half)


def degree_bucket(degree: pl.Expr) -> pl.Expr:
    """Bucket label of a degree of at least 1."""
    expr: pl.Expr = pl.lit(None, dtype=pl.String)
    for label, lowest in DEGREE_BUCKETS:
        expr = pl.when(degree >= lowest).then(pl.lit(label)).otherwise(expr)
    return expr


def bucket_labels() -> list[str]:
    return [label for label, _ in DEGREE_BUCKETS]


def group_labels(communities: pl.DataFrame, k: int) -> pl.DataFrame:
    """Re-key baseline communities to release group labels: communities of at least k persons
    become `G01…` by descending size (ties by community number, never by pseudonym); the rest,
    and unassigned persons, become `other`. Returns columns pid, group."""
    sizes = (
        communities.filter(pl.col("community") != UNASSIGNED_COMMUNITY)
        .group_by("community")
        .len()
        .filter(pl.col("len") >= k)
        .sort(["len", "community"], descending=[True, False])
    )
    labels = {
        community: f"{GROUP_PREFIX}{rank:02d}"
        for rank, community in enumerate(sizes.get_column("community").to_list(), start=1)
    }
    return communities.select(
        "pid",
        pl.col("community")
        .replace_strict(labels, default=OTHER_GROUP, return_dtype=pl.String)
        .alias("group"),
    )


def add_laplace(values: pl.Series, scale: float, rng: np.random.Generator) -> pl.Series:
    """Add zero-mean Laplace noise. Integer counts are rounded back to integers; the noise is
    symmetric, so rounding keeps the result unbiased. Nulls stay null; nothing is clipped,
    because clipping would bias the expectation."""
    noise = pl.Series(rng.laplace(0.0, scale, len(values)))
    noisy = values.cast(pl.Float64) + noise
    if values.dtype.is_integer():
        return noisy.round(0).cast(pl.Int64).alias(values.name)
    return noisy.alias(values.name)
