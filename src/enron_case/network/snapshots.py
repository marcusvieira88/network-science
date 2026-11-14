"""The person network and its weekly snapshots (docs/metrics.md, "The person network")."""

from __future__ import annotations

from datetime import date

import polars as pl

from enron_case.config import Config
from enron_case.contracts import vocab as v
from enron_case.errors import UsageError

WEEK = "week"
MONTH = "month"
PERIOD_INTERVALS = {WEEK: "1w", MONTH: "1mo"}
CORE_SCOPE, OBSERVED_SCOPE = v.CORE_SCOPE, v.OBSERVED_SCOPE


def stable_sum(expr: pl.Expr) -> pl.Expr:
    """Sum in sorted order: polars may hand a group's rows over in any order, and float
    addition is not associative, so plain sums differ between runs in the last bit."""
    return expr.sort().sum()


def period_interval(window: str) -> str:
    try:
        return PERIOD_INTERVALS[window]
    except KeyError as exc:
        raise UsageError(f"unknown window: {window}") from exc


def period_start(day: date, window: str) -> date:
    """First day of the period (Monday of the ISO week, or first of the month) holding `day`."""
    start = pl.Series([day]).dt.truncate(period_interval(window)).item()
    assert isinstance(start, date)
    return start


def sender_view(events: pl.DataFrame, entities_p: pl.DataFrame) -> pl.DataFrame:
    """In-network events from an internal person to a person (not themselves), with custodian
    flags for both ends."""
    custodians = entities_p.filter(pl.col("is_custodian")).get_column("pid").implode()
    return events.filter(
        pl.col("in_network"),
        pl.col("sender_type") == v.PERSON,
        pl.col("sender_internal"),
        pl.col("recipient_type") == v.PERSON,
        pl.col("sender_pid") != pl.col("recipient_pid"),
    ).with_columns(
        pl.col("sender_pid").is_in(custodians).alias("sender_custodian"),
        pl.col("recipient_pid").is_in(custodians).alias("recipient_custodian"),
    )


def person_network(view: pl.DataFrame, scope: str) -> pl.DataFrame:
    """Sender-view events forming ties of the person network in `scope`."""
    internal = view.filter(pl.col("recipient_internal"))
    if scope == CORE_SCOPE:
        return internal.filter(pl.col("sender_custodian"), pl.col("recipient_custodian"))
    return internal


def between(events: pl.DataFrame, start: date, end: date) -> pl.DataFrame:
    """Events whose date lies in `start .. end`, both inclusive."""
    return events.filter(pl.col("ts_hour").dt.date().is_between(start, end))


def with_period(events: pl.DataFrame, config: Config, window: str) -> pl.DataFrame:
    """Events in the analysis window, with their period start in column `week`."""
    return between(events, config.analysis_start, config.analysis_end).with_columns(
        pl.col("ts_hour").dt.date().dt.truncate(period_interval(window)).alias("week")
    )


def aggregate_ties(network: pl.DataFrame) -> pl.DataFrame:
    """One row per period and directed pair: summed weight and distinct messages."""
    return network.group_by("week", "sender_pid", "recipient_pid").agg(
        stable_sum(pl.col("weight")),
        pl.col("msg_pid").n_unique().cast(pl.Int64).alias("n_messages"),
    )


def build_snapshots(events: pl.DataFrame, entities_p: pl.DataFrame, config: Config) -> pl.DataFrame:
    """Rows of the `snapshots` table for both scopes, weekly."""
    view = with_period(sender_view(events, entities_p), config, WEEK)
    frames = [
        aggregate_ties(person_network(view, scope)).select(
            pl.lit(scope).alias("scope"),
            "week",
            pl.col("sender_pid").alias("src_pid"),
            pl.col("recipient_pid").alias("dst_pid"),
            "weight",
            "n_messages",
        )
        for scope in v.SCOPES
    ]
    return pl.concat(frames).sort("scope", "week", "src_pid", "dst_pid")
