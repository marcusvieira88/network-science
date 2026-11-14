"""Monthly record profile (finding/profile.py) on hand-built events with known answers."""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime

import polars as pl
import pytest

from enron_case.config import Config
from enron_case.finding import exploratory as ex
from enron_case.finding import profile
from enron_case.release import tables

A, B, C = "p_aaaaaaaaaaaaaaaa", "p_bbbbbbbbbbbbbbbb", "p_cccccccccccccccc"
CUSTODIANS = pl.Series([A, B])
SHORT = dataclasses.replace(
    Config(), analysis_start=date(2001, 2, 1), analysis_end=date(2001, 3, 31)
)


def _event(msg: str, when: datetime, sender: str, recipient: str) -> dict[str, object]:
    return {
        "msg_pid": msg,
        "ts_hour": when,
        "sender_pid": sender,
        "recipient_pid": recipient,
        "role": "to",
        "n_recipients": 1,
        "recipient_type": "person",
        "recipient_internal": True,
        "sender_internal": True,
    }


def _tables() -> ex.Tables:
    # Houston is UTC-6 in February: 15:00 UTC is 09:00 local, 03:00 UTC is 21:00 local the
    # day before. 2001-02-05 is a Monday; 2001-02-10 a Saturday.
    rows = [
        _event("m1", datetime(2001, 2, 5, 15, tzinfo=UTC), A, B),  # weekday, working hours
        _event("m2", datetime(2001, 2, 6, 3, tzinfo=UTC), A, C),  # weekday, 21:00: after hours
        _event("m3", datetime(2001, 2, 6, 16, tzinfo=UTC), B, A),  # weekday, working hours
        _event("m4", datetime(2001, 2, 10, 16, tzinfo=UTC), B, C),  # Saturday: not counted
        _event("m5", datetime(2001, 1, 9, 16, tzinfo=UTC), A, B),  # before the window
    ]
    events = pl.DataFrame(rows)
    return ex.Tables(ex.sent_messages(events, CUSTODIANS), ex.received_messages(events, CUSTODIANS))


def test_monthly_profile_counts_and_after_hours_share() -> None:
    out = profile.monthly_profile(_tables(), SHORT)
    assert out.get_column("month").to_list() == [date(2001, 2, 1), date(2001, 3, 1)]
    feb = out.row(0, named=True)
    assert feb["custodians_sending"] == 2
    assert feb["sent_messages"] == 4
    assert feb["after_hours_share"] == pytest.approx(1 / 3)  # one of three weekday messages
    assert feb["custodians_receiving"] == 2  # B (from A) and A (from B)
    assert feb["received_messages"] == 2
    march = out.row(1, named=True)
    assert march["sent_messages"] == 0
    assert march["after_hours_share"] is None


def test_release_suppresses_months_with_fewer_than_k_custodians() -> None:
    out = tables.record_profile(profile.monthly_profile(_tables(), SHORT), k_min=2)
    feb = out.row(0, named=True)
    assert feb["custodians_sending"] == 2 and feb["sent_messages"] == 4
    suppressed = tables.record_profile(profile.monthly_profile(_tables(), SHORT), k_min=3)
    row = suppressed.row(0, named=True)
    assert row["custodians_sending"] is None
    assert row["sent_messages"] is None
    assert row["after_hours_share"] is None
    assert row["received_messages"] is None
