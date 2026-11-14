"""The record section (report/record.py) on hand-built release tables with known answers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import polars as pl

from enron_case.report import record

MONTHS = [date(2000, m, 1) for m in range(8, 13)] + [date(2001, m, 1) for m in range(1, 13)]


def _profile(shares: Sequence[float | None]) -> pl.DataFrame:
    n = len(MONTHS)
    return pl.DataFrame(
        {
            "month": MONTHS,
            "custodians_sending": [10] * n,
            "sent_messages": list(range(100, 100 + n)),
            "after_hours_share": shares,
            "custodians_receiving": [12] * n,
            "received_messages": list(range(300, 300 + n)),
        }
    )


def _h5(median: float) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "hypothesis": ["H5", "H6"],
            "custodians": [32, 32],
            "median_change": [median, 0.0],
            "ci_low": [median - 0.05, -0.01],
            "ci_high": [median + 0.05, 0.01],
        }
    )


# Aug 2000 - Dec 2000, then Jan - Dec 2001: high until May 2001, low from June.
SWITCHED: list[float] = [
    0.5,
    0.45,
    0.55,
    0.48,
    0.5,
    0.5,
    0.47,
    0.5,
    0.56,
    0.6,
    0.25,
    0.14,
    0.1,
    0.07,
    0.06,
    0.06,
    0.09,
]


def test_ranges_switch_month_and_within_custodian_change() -> None:
    text = record.record_statement(_profile(SWITCHED), _h5(-0.44))
    # Reference months Aug-Nov 2000 and crisis months Aug-Nov 2001.
    assert "between 0.45 and 0.55 in the reference months" in text
    assert "between 0.06 and 0.1 in the crisis months" in text
    assert "do not overlap" in text
    # First month below the reference minimum from which every later month stays below it.
    assert "2001-06-01" in text
    assert "-0.44" in text and "32 custodians" in text


def test_overlapping_ranges_claim_no_change() -> None:
    flat = [0.5] * len(MONTHS)
    text = record.record_statement(_profile(flat), _h5(0.0))
    assert "overlap" in text and "do not overlap" not in text
    assert "no change of the timestamp convention is claimed" in text


def test_suppressed_months_are_ignored() -> None:
    shares: list[float | None] = list(SWITCHED)
    shares[1] = None  # Sep 2000 suppressed
    text = record.record_statement(_profile(shares), _h5(-0.44))
    assert "between 0.48 and 0.55 in the reference months" in text


def _h25(retention_passes: bool | None) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "hypothesis": ["H25"],
            "custodians": [30],
            "median_change": [0.02],
            "ci_low": [-0.01],
            "ci_high": [0.05],
            "p_holm": [1.0],
            "outcome": ["not supported"],
            "retention_passes": [retention_passes],
            "retention_median": [None if retention_passes is None else 0.01],
            "retention_ci_low": [None if retention_passes is None else -0.02],
            "retention_ci_high": [None if retention_passes is None else 0.04],
        }
    )


def test_replication_statement_reports_any_outcome() -> None:
    text = record.replication_statement(_h25(None))
    assert "median change of 0.02 (interval -0.01 to 0.05" in text
    assert "30 custodians" in text and "outcome: not supported" in text
    assert "retention check" not in text
    assert "retention check fails" in record.replication_statement(_h25(False))


def test_record_chart_skips_suppressed_months() -> None:
    shares: list[float | None] = list(SWITCHED)
    shares[0] = None
    chart = record.record_chart(_profile(shares))
    assert '"2000-08-01"' not in chart and '"2000-09-01"' in chart
    assert chart.startswith("```mermaid")


def test_record_summary_is_short_and_conditional() -> None:
    text = record.record_summary(_profile(SWITCHED), _h5(-0.44))
    assert "between 0.45 and 0.55 in the reference months" in text
    assert "from 2001-06-01" in text and "median change -0.44" in text
    assert len(text.split()) < 80
    flat = record.record_summary(_profile([0.5] * len(MONTHS)), _h5(0.0))
    assert flat == "No change of the timestamp convention between the two windows is claimed."


def test_switch_month_must_leave_the_whole_earlier_range() -> None:
    """April 2001 below the reference months but within the earlier spread is not the switch."""
    months = [date(2000, m, 1) for m in range(4, 13)] + [date(2001, m, 1) for m in range(1, 9)]
    shares = [0.38, 0.47, 0.40, 0.43, 0.46, 0.43, 0.45, 0.54, 0.5]
    shares += [0.49, 0.52, 0.49, 0.41, 0.37, 0.24, 0.10, 0.06]
    n = len(months)
    profile = pl.DataFrame(
        {
            "month": months,
            "custodians_sending": [10] * n,
            "sent_messages": [100] * n,
            "after_hours_share": shares,
            "custodians_receiving": [10] * n,
            "received_messages": [100] * n,
        }
    )
    assert "From 2001-05-01 on" in record.record_statement(profile, _h5(-0.44))
