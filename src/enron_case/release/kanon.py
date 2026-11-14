"""The single enforcement point for minimum group size and identifier patterns.

Builders use `suppress_below`, `drop_below` and `suppress_partition` to make a table
compliant; `check` verifies the result and `write` is the only way a release table reaches
disk. Every violation raises `PrivacyViolation` (exit code 6).
"""

from __future__ import annotations

import polars as pl

from enron_case.context import StageContext
from enron_case.contracts import schemas
from enron_case.contracts.vocab import DEFAULT_VARIANT
from enron_case.errors import PrivacyViolation

# Release columns that count persons; a published value must be at least k.
PERSON_COUNT_COLUMNS: dict[str, tuple[str, ...]] = {
    "weekly_metrics": ("n_active",),
    "degree_distribution": ("persons",),
    "community_groups": ("n_persons",),
    "risk": ("n_targets",),
}
# The metric whose value is itself a person count.
PERSON_COUNT_METRIC = "active_persons"
# Tables whose partition total an attacker can learn elsewhere (the public corpus gives the
# number of active persons per period), so one lone suppressed cell would be recoverable.
DIFFERENCING_PARTITIONS: dict[str, str] = {"degree_distribution": "period"}


def suppress_below(
    df: pl.DataFrame, count_col: str, k: int, dependents: tuple[str, ...] = ()
) -> pl.DataFrame:
    """Null `count_col`, and every column derived from it, where the count is below k."""
    keep = pl.col(count_col) >= k
    return df.with_columns(pl.when(keep).then(pl.col(c)).alias(c) for c in (count_col, *dependents))


def drop_below(df: pl.DataFrame, count_col: str, k: int) -> pl.DataFrame:
    """Drop rows that describe fewer than k persons."""
    return df.filter(pl.col(count_col) >= k)


def suppress_partition(df: pl.DataFrame, count_col: str, partition: str, k: int) -> pl.DataFrame:
    """Suppress counts below k, then protect each partition against differencing: where it hides
    exactly one cell with a true value above zero, also suppress its smallest published cell,
    so the partition total minus the published cells does not reveal that count. A hidden true
    zero is no protection, as the difference still equals the one small count. A partition
    hiding a single cell of any value is complemented too, because `check` cannot tell a
    hidden zero from a hidden small count."""
    true = pl.col(count_col)
    # A cell that is already null was suppressed earlier; its value is unknown, so it counts as
    # a hidden non-zero cell.
    small = true.is_null() | (true < k)
    positive_hidden = (small & (true.is_null() | (true > 0))).sum().over(partition)
    lone = (positive_hidden == 1) | (small.sum().over(partition) == 1)
    smallest = ~small & (true == true.filter(~small).min().over(partition))
    first_smallest = smallest & (smallest.cum_sum().over(partition) == 1)
    hide = small | (lone & first_smallest)
    return df.with_columns(pl.when(hide).then(None).otherwise(true).alias(count_col))


def assert_no_identifiers(df: pl.DataFrame) -> None:
    hits = schemas.leak_count(df)
    if hits:
        raise PrivacyViolation(f"{hits} identifier-shaped values in a release table")


def check(name: str, df: pl.DataFrame, k: int) -> None:
    """Raise PrivacyViolation unless `df` is publishable as release table `name`."""
    assert_no_identifiers(df)
    for col in PERSON_COUNT_COLUMNS.get(name, ()):
        if (df.get_column(col).drop_nulls() < k).any():
            raise PrivacyViolation(f"{name}.{col}: a person count below k")
    if name == "weekly_metrics":
        _check_metric_values(df, k)
    partition = DIFFERENCING_PARTITIONS.get(name)
    if partition is not None:
        _check_differencing(df, PERSON_COUNT_COLUMNS[name][0], partition)


def _check_metric_values(df: pl.DataFrame, k: int) -> None:
    orphaned = df.filter(pl.col("value").is_not_null() & pl.col("n_active").is_null())
    if orphaned.height:
        raise PrivacyViolation(f"weekly_metrics: {orphaned.height} values from suppressed groups")
    small = df.filter((pl.col("metric") == PERSON_COUNT_METRIC) & (pl.col("value") < k))
    if small.height:
        raise PrivacyViolation(f"weekly_metrics: {small.height} person counts below k")
    variants = df.filter(pl.col("variant") != DEFAULT_VARIANT)
    if variants.height:
        raise PrivacyViolation(f"weekly_metrics: {variants.height} rows of a non-default variant")


def _check_differencing(df: pl.DataFrame, count_col: str, partition: str) -> None:
    cells = df.group_by(partition).agg(
        pl.col(count_col).null_count().alias("suppressed"),
        pl.col(count_col).count().alias("published"),
    )
    lone = cells.filter((pl.col("suppressed") == 1) & (pl.col("published") > 0))
    if lone.height:
        raise PrivacyViolation(f"{lone.height} partitions with one recoverable suppressed cell")


def enforce(name: str, df: pl.DataFrame, k: int) -> pl.DataFrame:
    """Conform `df` to its release contract and check it. Returns the conformed table."""
    out = schemas.conform(df, name)
    check(name, out, k)
    return out


def write(ctx: StageContext, name: str, df: pl.DataFrame) -> pl.DataFrame:
    """The only path from a release builder to disk."""
    return ctx.write(name, enforce(name, df, ctx.config.k_min))
