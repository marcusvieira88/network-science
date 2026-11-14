"""Report section "what changed in the record during the crisis year" (`record_profile`, H5).

Every comparison of H5–H25 sets the crisis weeks against the same weeks a year earlier. This
section shows what the record itself does between those windows: how much mail it holds and
when in the day the custodians' weekday sent mail is stamped. A shift of several hours in the
second, within the same people, is a change in how `Date` was recorded, not in behaviour.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import polars as pl

from enron_case.config import CRISIS_WINDOW, REFERENCE_WINDOW
from enron_case.report.markdown import format_value, table

SHARE = "after_hours_share"
TIMESTAMP_HYPOTHESIS = (
    "H5"  # the within-custodian after-hours share (docs/hypotheses-exploratory.md)
)
PROFILE_HEADERS = (
    "Month",
    "Custodians sending",
    "Sent",
    "After-hours share (weekdays)",
    "Custodians receiving",
    "Received",
)
PROFILE_COLUMNS = (
    "month",
    "custodians_sending",
    "sent_messages",
    SHARE,
    "custodians_receiving",
    "received_messages",
)


def _months_of(profile: pl.DataFrame, window: tuple[date, date], column: str) -> list[float]:
    """Published values of `column` in the months that start a window's month, up to the month
    holding its end (exclusive): Aug–Nov for a window from mid-August to early December."""
    first, last = window[0].replace(day=1), window[1].replace(day=1)
    rows = profile.filter(
        (pl.col("month") >= first) & (pl.col("month") < last) & pl.col(column).is_not_null()
    )
    return [float(v) for v in rows.get_column(column).to_list()]


def _span(values: Sequence[float]) -> str:
    return f"between {format_value(min(values))} and {format_value(max(values))}"


def _switch_month(profile: pl.DataFrame, reference: Sequence[float], lower: bool) -> date | None:
    """First month after the reference window from which every published month lies beyond
    the reference range on the crisis side."""
    later = profile.filter(
        (pl.col("month") >= REFERENCE_WINDOW[1].replace(day=1)) & pl.col(SHARE).is_not_null()
    ).sort("month")
    months = later.get_column("month").to_list()
    shares = [float(v) for v in later.get_column(SHARE).to_list()]
    beyond = [s < min(reference) if lower else s > max(reference) for s in shares]
    for index in range(len(months)):
        if all(beyond[index:]):
            month: date = months[index]
            return month
    return None


def _volume_sentence(profile: pl.DataFrame) -> str:
    parts = []
    for column, label in (("sent_messages", "sent"), ("received_messages", "received")):
        reference = _months_of(profile, REFERENCE_WINDOW, column)
        crisis = _months_of(profile, CRISIS_WINDOW, column)
        if reference and crisis:
            parts.append(
                f"{label} messages per month {_span(reference)} in the reference months and "
                f"{_span(crisis)} in the crisis months"
            )
    if not parts:
        return ""
    return " Mail kept: " + "; ".join(parts) + "."


def _within_custodian(exploratory: pl.DataFrame) -> str:
    rows = exploratory.filter(pl.col("hypothesis") == TIMESTAMP_HYPOTHESIS).rows(named=True)
    if not rows or rows[0]["median_change"] is None:
        return ""
    row = rows[0]
    return (
        f" Within the same people ({TIMESTAMP_HYPOTHESIS}, {format_value(row['custodians'])} "
        f"custodians) the share changes by a median of {format_value(row['median_change'])} "
        f"(interval {format_value(row['ci_low'])} to {format_value(row['ci_high'])}), so it is "
        "not a change in who is in the data."
    )


def record_statement(profile: pl.DataFrame, exploratory: pl.DataFrame) -> str:
    reference = _months_of(profile, REFERENCE_WINDOW, SHARE)
    crisis = _months_of(profile, CRISIS_WINDOW, SHARE)
    if not reference or not crisis:
        return "Too few months are published to compare the record between the two windows."
    ranges = (
        f"The share of the custodians' weekday sent mail stamped outside working hours is "
        f"{_span(reference)} in the reference months and {_span(crisis)} in the crisis months"
    )
    lower = max(crisis) < min(reference)
    if not lower and min(crisis) <= max(reference):
        return (
            f"{ranges}: the ranges overlap, so no change of the timestamp convention is claimed."
            + _volume_sentence(profile)
        )
    switch = _switch_month(profile, reference, lower)
    switch_text = (
        f" It moves beyond the reference range for good from {format_value(switch)} on."
        if switch is not None
        else ""
    )
    return (
        f"{ranges}: the ranges do not overlap.{switch_text}{_within_custodian(exploratory)} "
        "Working days do not move by hours within a year: the `Date` header was recorded "
        "under a different convention after the change, and every comparison of H5–H25 sets "
        "a window after it against a window before it. The pre-crisis placebo compares two "
        "windows before it, so it cannot detect an artifact of that change."
        + _volume_sentence(profile)
    )


def profile_table(profile: pl.DataFrame) -> str:
    rows = profile.select(PROFILE_COLUMNS).rows()
    return table(PROFILE_HEADERS, [[format_value(v) for v in row] for row in rows])


def record_section(profile: pl.DataFrame, exploratory: pl.DataFrame) -> str:
    return "\n\n".join(
        (
            "## What changed in the record during the crisis year",
            "Descriptive, added in the review after every hypothesis result was known. Every "
            "within-custodian comparison sets the crisis weeks against the same weeks a year "
            "earlier, so it inherits any change in how the record was kept between them. Per "
            "month, over the custodians: how many sent and received mail, how much, and the "
            "share of their weekday sent mail stamped outside working hours in Houston time "
            "(the H5 definition). Months with fewer than k custodians on a side are suppressed.",
            record_statement(profile, exploratory),
            profile_table(profile),
        )
    )
