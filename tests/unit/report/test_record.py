"""The record section (report/record.py) on hand-built release tables with known answers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import polars as pl

from enron_case.config import PRIOR_WORK_YEAR
from enron_case.contracts import vocab
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


def test_record_statement_names_h1_to_h4_as_crossing_the_change_too() -> None:
    text = record.record_statement(_profile(SWITCHED), _h5(-0.44))
    assert "H1–H4 compare the weeks after their change week with the baseline year" in text


TOO_FEW = "Too few months are published to compare the record between the two windows."
# SWITCHED with December 2001 back above the reference minimum: no month from which every
# later month stays below it, so no switch month is named.
NO_SWITCH: list[float] = [*SWITCHED[:-1], 0.6]
NO_H5 = pl.DataFrame({"hypothesis": ["H6"], "custodians": [32], "median_change": [0.0]})
# August to November 2000: the reference months, and every published month before December 2000.
REFERENCE_MONTHS = (date(2000, 8, 1), date(2000, 11, 1))
RANGES = (
    "The share of the custodians' weekday sent mail stamped outside working hours is between "
    "0.45 and 0.55 in the reference months and between 0.06 and 0.1 in the crisis months"
)


def _months_suppressed(shares: Sequence[float | None], first: date, last: date) -> pl.DataFrame:
    """The profile with the after-hours share suppressed in months first..last (inclusive)."""
    hidden = pl.col("month").is_between(first, last)
    return _profile(shares).with_columns(
        pl.when(hidden).then(None).otherwise(pl.col(record.SHARE)).alias(record.SHARE)
    )


def test_suppressed_crisis_months_leave_too_few_to_compare() -> None:
    profile = _months_suppressed(SWITCHED, date(2001, 8, 1), date(2001, 11, 1))
    assert record.record_statement(profile, _h5(-0.44)) == TOO_FEW
    assert record.record_summary(profile, _h5(-0.44)) == TOO_FEW


def test_suppressed_reference_months_leave_too_few_to_compare() -> None:
    profile = _months_suppressed(SWITCHED, *REFERENCE_MONTHS)
    assert record.record_statement(profile, _h5(-0.44)) == TOO_FEW
    assert record.record_summary(profile, _h5(-0.44)) == TOO_FEW


def test_summary_without_h5_says_not_measured_and_names_no_switch() -> None:
    text = record.record_summary(_profile(NO_SWITCH), NO_H5)
    assert text == (
        "The share of weekday sent mail stamped outside working hours is between 0.45 and 0.55 "
        "in the reference months and between 0.06 and 0.1 in the crisis months; the `Date` "
        "convention changed in between, within the same people (not measured). Every "
        "within-custodian comparison crosses that change."
    )


def test_summary_with_suppressed_h5_says_not_measured() -> None:
    suppressed = _h5(-0.44).with_columns(pl.lit(None, pl.Float64).alias("median_change"))
    assert "within the same people (not measured)" in record.record_summary(
        _profile(SWITCHED), suppressed
    )


def test_statement_without_switch_h5_or_volumes_keeps_only_the_ranges_and_caveat() -> None:
    """No switch month, no H5 row and no published mail volume in either window: the
    statement goes straight from the ranges to the caveat and ends without a volume part."""
    profile = _profile(NO_SWITCH).with_columns(
        pl.lit(None, pl.Int64).alias("sent_messages"),
        pl.lit(None, pl.Int64).alias("received_messages"),
    )
    text = record.record_statement(profile, NO_H5)
    assert text.startswith(
        f"{RANGES}: the ranges do not overlap. Working days do not move by hours within a year:"
    )
    assert text.endswith(
        "folder names would show it, and each is reduced at once to one of four classes and "
        "never kept."
    )
    assert "do not read" not in text
    assert "From " not in text and "Within the same people" not in text


def test_volume_sentence_skips_a_side_suppressed_in_one_window() -> None:
    """Sent mail suppressed in the crisis months: only received mail is compared. Received is
    300 + month index: Aug-Nov 2000 are indices 0-3, Aug-Nov 2001 are indices 12-15."""
    profile = _profile(SWITCHED).with_columns(
        pl.when(pl.col("month") >= date(2001, 8, 1))
        .then(None)
        .otherwise(pl.col("sent_messages"))
        .alias("sent_messages")
    )
    text = record.record_statement(profile, _h5(-0.44))
    assert text.endswith(
        " Mail kept: received messages per month between 300 and 303 in the reference months "
        "and between 312 and 315 in the crisis months."
    )


def test_switch_month_needs_a_published_month_before_the_reference_end() -> None:
    """Every month before December 2000 suppressed: there is nothing to lie beyond."""
    profile = _months_suppressed(SWITCHED, *REFERENCE_MONTHS)
    assert record._switch_month(profile, lower=True) is None


def test_replication_statement_when_h25_was_not_run() -> None:
    assert record.replication_statement(NO_H5) == (
        "The replication test of prior work was not run."
    )


def test_replication_statement_when_h25_is_suppressed() -> None:
    suppressed = _h25(None).with_columns(pl.lit(None, pl.Float64).alias("median_change"))
    assert record.replication_statement(suppressed) == (
        "H25 (the replication test of prior work) is suppressed: fewer than k custodians "
        "could be compared."
    )


# ---- the finding, its confidence rule and the reading of H5 ----------------------------------


def test_confidence_is_high_only_when_ranges_part_and_h5_excludes_zero() -> None:
    """SWITCHED: reference months 0.45-0.55, crisis months 0.06-0.1, so the ranges do not
    overlap and the share fell. `_h5(m)` has the interval m ± 0.05."""
    profile = _profile(SWITCHED)
    assert record.record_confidence(profile, _h5(-0.44)) == "high"  # -0.49 to -0.39
    assert record.record_confidence(profile, _h5(-0.02)) == "moderate"  # -0.07 to 0.03
    assert record.record_confidence(profile, _h5(0.44)) == "high"  # 0.39 to 0.49
    assert record.record_confidence(profile, NO_H5) == "moderate"  # not measured


def test_confidence_reads_a_rise_of_the_share_the_same_way() -> None:
    """The mirror case: crisis months above every reference month, H5 above zero."""
    profile = _profile([1 - share for share in SWITCHED])
    assert record.record_confidence(profile, _h5(0.44)) == "high"
    assert record.record_confidence(profile, _h5(0.0)) == "moderate"


def test_no_confidence_and_no_finding_without_a_claimed_change() -> None:
    flat = _profile([0.5] * len(MONTHS))
    assert record.record_confidence(flat, _h5(-0.44)) is None
    assert record.finding_statement(flat, _h5(-0.44)) == ""
    hidden = _months_suppressed(SWITCHED, *REFERENCE_MONTHS)
    assert record.record_confidence(hidden, _h5(-0.44)) is None


def test_finding_statement_names_the_record_change_and_its_derived_confidence() -> None:
    assert record.finding_statement(_profile(SWITCHED), _h5(-0.44)) == (
        "The finding: the record changed (high confidence that it changed; cause not established)."
    )
    assert "(moderate confidence that it changed;" in record.finding_statement(
        _profile(SWITCHED), NO_H5
    )


def test_statement_states_the_confidence_with_its_rule() -> None:
    text = record.record_statement(_profile(SWITCHED), _h5(-0.44))
    assert f"Confidence that the record changed: high (the rule: {record.CONFIDENCE_RULE})" in text
    assert "moderate (the rule:" in record.record_statement(_profile(SWITCHED), NO_H5)


def test_h5_estimate_is_read_as_a_measurement_of_the_record_not_of_behaviour() -> None:
    """H5 is untestable as a behavioural hypothesis, yet its number is the evidence here: the
    statement and the summary say which reading applies."""
    text = record.record_statement(_profile(SWITCHED), _h5(-0.44))
    assert (
        "As a hypothesis about behaviour, H5 could not be tested, because the convention "
        "changed under it; the same number is read here as a measurement of the record, not "
        "of behaviour."
    ) in text
    summary = record.record_summary(_profile(SWITCHED), _h5(-0.44))
    assert "read as a measurement of the record, not of behaviour" in summary


def test_folder_names_wording_matches_the_number_of_folder_classes() -> None:
    assert len(vocab.FOLDER_CLASSES) == 4
    assert "one of four classes" in record.FOLDER_NAMES


def test_replication_statement_names_prior_work_neutrally() -> None:
    text = record.replication_statement(_h25(None))
    assert text.startswith(
        "H25, the post-hoc replication test of the denser crisis-period network that Diesner "
        f"and Carley ({PRIOR_WORK_YEAR}) report from a comparison of single months of this "
        "corpus, compares each custodian's share"
    )
    assert "Frantz" not in text


def test_replication_summary_is_the_outcome_in_a_few_words() -> None:
    assert record.replication_summary(_h25(None)) == (
        "H25 (post-hoc replication test of prior work): median change 0.02 (interval -0.01 to "
        "0.05); outcome: not supported."
    )
    assert record.replication_summary(NO_H5) == "The replication test of prior work was not run."
