"""Release mitigations: time coarsening, degree bucketing, group re-keying and noise.

Pure functions over polars data. Minimum group size itself is enforced in `kanon`.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from enron_case.contracts.vocab import OTHER_GROUP, UNASSIGNED_COMMUNITY

LAST_MONTH_OF_FIRST_HALF = 6
GROUP_PREFIX = "G"


def half_year(week: pl.Expr) -> pl.Expr:
    """`2000H1` / `2000H2` label of the half-year a week's Monday falls in."""
    half = pl.when(week.dt.month() <= LAST_MONTH_OF_FIRST_HALF).then(1).otherwise(2)
    return pl.format("{}H{}", week.dt.year(), half)


def degree_buckets(floors: tuple[int, ...]) -> list[tuple[str, int]]:
    """(label, lowest degree) per bucket from ascending floors: `(1, 2, 5, 10)` gives
    `1`, `2-4`, `5-9` and `10+`."""
    ceilings = [floor - 1 for floor in floors[1:]]
    labels = [
        str(low) if low == high else f"{low}-{high}"
        for low, high in zip(floors, ceilings, strict=False)
    ]
    return list(zip([*labels, f"{floors[-1]}+"], floors, strict=True))


def degree_bucket(degree: pl.Expr, floors: tuple[int, ...]) -> pl.Expr:
    """Bucket label of a degree of at least the lowest floor."""
    expr: pl.Expr = pl.lit(None, dtype=pl.String)
    for label, lowest in degree_buckets(floors):
        expr = pl.when(degree >= lowest).then(pl.lit(label)).otherwise(expr)
    return expr


def bucket_labels(floors: tuple[int, ...]) -> list[str]:
    return [label for label, _ in degree_buckets(floors)]


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
