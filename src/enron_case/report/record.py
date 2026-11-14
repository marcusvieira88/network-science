"""Report section "what changed in the record during the crisis year" (`record_profile`, H5).

Every comparison of H5–H25 sets the crisis weeks against the same weeks a year earlier. This
section shows what the record itself does between those windows: how much mail it holds and
when in the day the custodians' weekday sent mail is stamped. A shift of several hours in the
second, within the same people, is a change in how `Date` was recorded, not in behaviour.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

import polars as pl

from enron_case.config import CRISIS_WINDOW, PRIOR_WORK_YEAR, REFERENCE_WINDOW
from enron_case.contracts import vocab
from enron_case.report.markdown import format_value, table
from enron_case.report.quality import FOLDER_NAME_RULE

SHARE = "after_hours_share"
TIMESTAMP_HYPOTHESIS = (
    "H5"  # the within-custodian after-hours share (docs/hypotheses-exploratory.md)
)
HIGH, MODERATE, _ = vocab.CONFIDENCE
# How sure we are that the record changed, as a rule on published numbers (not a judgment).
CONFIDENCE_RULE = (
    f"{HIGH} when the monthly ranges of the two windows do not overlap and the change within "
    f"the same people ({TIMESTAMP_HYPOTHESIS}) has an interval that excludes zero; {MODERATE} "
    "when the ranges do not overlap but that change is not measured or its interval includes "
    "zero; with overlapping ranges no change is claimed"
)
FOLDER_NAMES = f"each is {FOLDER_NAME_RULE}"
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


def _switch_month(profile: pl.DataFrame, lower: bool) -> date | None:
    """First month after the reference window from which every published month lies beyond
    every month up to the window's end, on the crisis side: beyond anything the record showed
    before, not only beyond the few reference months."""
    end = REFERENCE_WINDOW[1].replace(day=1)
    published = profile.filter(pl.col(SHARE).is_not_null()).sort("month")
    before = [float(v) for v in published.filter(pl.col("month") < end).get_column(SHARE)]
    later = published.filter(pl.col("month") >= end)
    if not before:
        return None
    months = later.get_column("month").to_list()
    shares = [float(v) for v in later.get_column(SHARE).to_list()]
    beyond = [s < min(before) if lower else s > max(before) for s in shares]
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


Row = Mapping[str, object]


def _timestamp_row(exploratory: pl.DataFrame) -> Row | None:
    """The published within-custodian change of the after-hours share, or None when it was not
    run or is suppressed."""
    rows = exploratory.filter(pl.col("hypothesis") == TIMESTAMP_HYPOTHESIS).rows(named=True)
    if not rows or rows[0]["median_change"] is None:
        return None
    return rows[0]


def _excludes_zero(row: Row) -> bool:
    """The within-custodian interval lies wholly on one side of zero."""
    low, high = row["ci_low"], row["ci_high"]
    if not isinstance(low, int | float) or not isinstance(high, int | float):
        return False
    return low > 0 or high < 0


def _within_custodian(exploratory: pl.DataFrame) -> str:
    """The change within the same people, read by what its interval allows: only an interval
    that excludes zero rules out a change in who is in the data."""
    row = _timestamp_row(exploratory)
    if row is None:
        return ""
    measured = (
        f" Within the same people ({TIMESTAMP_HYPOTHESIS}, {format_value(row['custodians'])} "
        f"custodians) the share changes by a median of {format_value(row['median_change'])} "
        f"(interval {format_value(row['ci_low'])} to {format_value(row['ci_high'])})"
    )
    if not _excludes_zero(row):
        return (
            f"{measured}: the interval includes zero, so a change in who is in the data is not "
            "ruled out."
        )
    return (
        f"{measured}, so it is not a change in who is in the data. As a hypothesis about "
        f"behaviour, {TIMESTAMP_HYPOTHESIS} could not be tested, because the convention "
        "changed under it; the same number is read here as a measurement of the record, not "
        "of behaviour."
    )


def _lower(reference: Sequence[float], crisis: Sequence[float]) -> bool | None:
    """True when every crisis month lies below every reference month, False when above; None
    when the two ranges overlap, so no change is claimed."""
    if max(crisis) < min(reference):
        return True
    return False if min(crisis) > max(reference) else None


def record_confidence(profile: pl.DataFrame, exploratory: pl.DataFrame) -> str | None:
    """Confidence that the record changed between the windows, by CONFIDENCE_RULE; None when
    no change is claimed (overlapping ranges, or too few published months)."""
    reference = _months_of(profile, REFERENCE_WINDOW, SHARE)
    crisis = _months_of(profile, CRISIS_WINDOW, SHARE)
    if not reference or not crisis:
        return None
    if _lower(reference, crisis) is None:
        return None
    row = _timestamp_row(exploratory)
    return HIGH if row is not None and _excludes_zero(row) else MODERATE


def finding_statement(profile: pl.DataFrame, exploratory: pl.DataFrame) -> str:
    """The finding in one sentence, or "" when no change of the record is claimed."""
    confidence = record_confidence(profile, exploratory)
    if confidence is None:
        return ""
    return (
        f"The finding: the record changed ({confidence} confidence that it changed; cause not "
        "established)."
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
    lower = _lower(reference, crisis)
    if lower is None:
        return (
            f"{ranges}: the ranges overlap, so no change of the timestamp convention is claimed."
            + _volume_sentence(profile)
        )
    switch = _switch_month(profile, lower)
    switch_text = (
        f" From {format_value(switch)} on, every month lies beyond every month up to the end "
        "of the reference window."
        if switch is not None
        else ""
    )
    return (
        f"{ranges}: the ranges do not overlap.{switch_text}{_within_custodian(exploratory)} "
        "Working days do not move by hours within a year: the `Date` header was recorded "
        "under a different convention after the change, and every comparison of H5–H25 sets "
        "a window after it against a window before it; H1–H4 compare the weeks after their change "
        "week with the baseline year, so they span it too. The pre-crisis placebo compares two "
        "windows before it, so it cannot detect an artifact of that change. Confidence that "
        f"the record changed: {record_confidence(profile, exploratory)} (the rule: "
        f"{CONFIDENCE_RULE}). Its cause, most likely a change of mail system, is not "
        f"established: folder names would show it, and {FOLDER_NAMES}." + _volume_sentence(profile)
    )


def record_summary(profile: pl.DataFrame, exploratory: pl.DataFrame) -> str:
    """The evidence behind `finding_statement` in two sentences, for the one-page decision
    record, which states the confidence once, in that statement."""
    reference = _months_of(profile, REFERENCE_WINDOW, SHARE)
    crisis = _months_of(profile, CRISIS_WINDOW, SHARE)
    if not reference or not crisis:
        return "Too few months are published to compare the record between the two windows."
    lower = _lower(reference, crisis)
    if lower is None:
        return "No change of the timestamp convention between the two windows is claimed."
    switch = _switch_month(profile, lower)
    since = f" from {format_value(switch)}" if switch is not None else ""
    return (
        f"The share of weekday sent mail stamped outside working hours is {_span(reference)} "
        f"in the reference months and {_span(crisis)} in the crisis months; the `Date` "
        f"convention changed in between{since} ({_within_custodian_short(exploratory)}). "
        "Every within-custodian comparison crosses that change."
    )


def _within_custodian_short(exploratory: pl.DataFrame) -> str:
    row = _timestamp_row(exploratory)
    if row is None:
        return "the change within the same people is not measured"
    estimate = (
        f"{TIMESTAMP_HYPOTHESIS}: median change {format_value(row['median_change'])}, interval "
        f"{format_value(row['ci_low'])} to {format_value(row['ci_high'])}"
    )
    if not _excludes_zero(row):
        return f"within the same people it is not established; {estimate}"
    return (
        f"within the same people; {estimate}, read as a measurement of the record, not of behaviour"
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
            f"(the {TIMESTAMP_HYPOTHESIS} definition). Months with fewer than k custodians on a "
            "side are suppressed.",
            record_statement(profile, exploratory),
            profile_table(profile),
        )
    )


REPLICATION_HYPOTHESIS = "H25"  # the post-hoc replication test of PRIOR_WORK
# Diesner & Carley (the SIAM workshop paper) report the density comparison of two single
# months; Diesner, Frantz & Carley of the same year say density does not track the scandal
# (verified against both papers; docs/hypotheses-exploratory.md).
PRIOR_WORK = (
    f"the denser crisis-period network that Diesner and Carley ({PRIOR_WORK_YEAR}) report "
    "from a comparison of single months of this corpus"
)


def replication_statement(exploratory: pl.DataFrame) -> str:
    """H25's outcome in one sentence, whatever it is."""
    rows = exploratory.filter(pl.col("hypothesis") == REPLICATION_HYPOTHESIS).rows(named=True)
    if not rows:
        return "The replication test of prior work was not run."
    row = rows[0]
    if row["median_change"] is None:
        return (
            f"{REPLICATION_HYPOTHESIS} (the replication test of prior work) is suppressed: "
            "fewer than k custodians could be compared."
        )
    text = (
        f"{REPLICATION_HYPOTHESIS}, the post-hoc replication test of {PRIOR_WORK}, compares "
        "each custodian's share of the other custodians they exchanged mail with: a median "
        "change of "
        f"{format_value(row['median_change'])} (interval {format_value(row['ci_low'])} to "
        f"{format_value(row['ci_high'])}, Holm-adjusted p = {format_value(row['p_holm'])}, "
        f"{format_value(row['custodians'])} custodians); outcome: {row['outcome']}"
    )
    if row["retention_passes"] is not None:
        text += (
            f"; counting only the custodians written to, the change is "
            f"{format_value(row['retention_median'])} (interval "
            f"{format_value(row['retention_ci_low'])} to "
            f"{format_value(row['retention_ci_high'])}), and the retention check "
            f"{'passes' if row['retention_passes'] else 'fails'}"
        )
    return text + "."


def replication_summary(exploratory: pl.DataFrame) -> str:
    """H25's outcome in a few words, for the one-page decision record."""
    rows = exploratory.filter(pl.col("hypothesis") == REPLICATION_HYPOTHESIS).rows(named=True)
    if not rows or rows[0]["median_change"] is None:
        return replication_statement(exploratory)
    row = rows[0]
    return (
        f"{REPLICATION_HYPOTHESIS} (post-hoc replication test of prior work): median change "
        f"{format_value(row['median_change'])} (interval {format_value(row['ci_low'])} to "
        f"{format_value(row['ci_high'])}); outcome: {row['outcome']}."
    )


def record_chart(profile: pl.DataFrame) -> str:
    """Mermaid line chart of the after-hours share by month (published months only)."""
    rows = profile.filter(pl.col(SHARE).is_not_null()).sort("month")
    months = ", ".join(f'"{format_value(m)}"' for m in rows.get_column("month").to_list())
    shares = ", ".join(format_value(v) for v in rows.get_column(SHARE).to_list())
    return "\n".join(
        (
            "```mermaid",
            "xychart-beta",
            '    title "Weekday sent mail stamped outside working hours, share by month"',
            f"    x-axis [{months}]",
            f"    line [{shares}]",
            "```",
        )
    )
