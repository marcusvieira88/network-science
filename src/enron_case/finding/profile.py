"""Monthly profile of the custodians' mail record (descriptive; docs/hypotheses-exploratory.md).

Two properties of the record that every comparison across 2001 inherits: how much of the
custodians' mail each month holds, and at what local hour their weekday sent mail is stamped.
A jump in the second marks a change in how the `Date` header was recorded, not in behaviour:
people do not move their working day by several hours from one month to the next.
"""

from __future__ import annotations

import polars as pl

from enron_case.config import Config
from enron_case.finding import exploratory
from enron_case.network.snapshots import MONTH, period_interval, period_start

COUNT_COLUMNS = ("custodians_sending", "sent_messages", "custodians_receiving", "received_messages")


def _by_month(df: pl.DataFrame, config: Config) -> pl.DataFrame:
    return df.filter(pl.col("day").is_between(config.analysis_start, config.analysis_end))


def monthly_profile(tables: exploratory.Tables, config: Config) -> pl.DataFrame:
    """One row per month of the analysis window (local time), every month present."""
    interval = period_interval(MONTH)
    month = pl.col("day").dt.truncate(interval).alias("month")
    sent = _by_month(tables.sent, config).with_columns(month)
    weekday = pl.col("weekday") <= exploratory.LAST_WEEKDAY
    sending = sent.group_by("month").agg(
        pl.col("pid").n_unique().alias("custodians_sending"),
        pl.len().alias("sent_messages"),
        exploratory.after_hours.filter(weekday).cast(pl.Float64).mean().alias("after_hours_share"),
    )
    receiving = (
        _by_month(tables.received, config)
        .with_columns(month)
        .group_by("month")
        .agg(
            pl.col("pid").n_unique().alias("custodians_receiving"),
            pl.len().alias("received_messages"),
        )
    )
    months = pl.date_range(
        period_start(config.analysis_start, MONTH), config.analysis_end, interval, eager=True
    ).alias("month")
    return (
        pl.DataFrame(months)
        .join(sending, on="month", how="left")
        .join(receiving, on="month", how="left")
        .with_columns(pl.col(c).fill_null(0).cast(pl.Int64) for c in COUNT_COLUMNS)
        .select("month", *COUNT_COLUMNS[:2], "after_hours_share", *COUNT_COLUMNS[2:])
        .sort("month")
    )
