"""Exploratory measures (finding/exploratory.py) on hand-built events with known answers."""

from __future__ import annotations

from datetime import UTC, date, datetime

import numpy as np
import polars as pl

from enron_case.finding import exploratory as ex

A, B, C, D = "p_aaaaaaaaaaaaaaaa", "p_bbbbbbbbbbbbbbbb", "p_cccccccccccccccc", "p_dddddddddddddddd"
L = "p_llllllllllllllll"  # a list address
CUSTODIANS = pl.Series([A, B])
WINDOW = (date(2001, 9, 3), date(2001, 9, 30))


def _event(
    msg: str,
    day: int,
    sender: str,
    recipient: str,
    n: int = 1,
    month: int = 9,
    role: str = "to",
    rtype: str = "person",
    internal: bool = True,
    sender_internal: bool = True,
) -> dict[str, object]:
    return {
        "msg_pid": msg,
        "ts_hour": datetime(2001, month, day, 15, tzinfo=UTC),
        "sender_pid": sender,
        "recipient_pid": recipient,
        "role": role,
        "n_recipients": n,
        "recipient_type": rtype,
        "recipient_internal": internal,
        "sender_internal": sender_internal,
    }


def _tables(rows: list[dict[str, object]]) -> ex.Tables:
    events = pl.DataFrame(rows)
    return ex.Tables(ex.sent_messages(events, CUSTODIANS), ex.received_messages(events, CUSTODIANS))


def _value(df: pl.DataFrame, pid: str) -> float:
    return float(df.filter(pl.col("pid") == pid).get_column("value").item())


def test_reciprocity_counts_contacts_who_wrote_back() -> None:
    tables = _tables(
        [
            _event("m1", 4, A, C),
            _event("m2", 5, A, D),  # A writes to C and D
            _event("m3", 6, C, A),  # only C writes back
        ]
    )
    assert _value(ex.MEASURES["E12"](tables, WINDOW), A) == 0.5


def test_new_contact_share_uses_the_lookback() -> None:
    tables = _tables(
        [
            _event("m0", 10, A, C, month=7),  # C known from July
            _event("m1", 4, A, C),
            _event("m2", 5, A, D),  # D is new in the window
        ]
    )
    assert _value(ex.MEASURES["E15"](tables, WINDOW), A) == 0.5


def test_new_contact_share_needs_a_history() -> None:
    tables = _tables([_event("m1", 4, A, C)])
    assert ex.MEASURES["E15"](tables, WINDOW).filter(pl.col("pid") == A).is_empty()


def test_active_week_share() -> None:
    # Window 2001-09-03 .. 2001-09-30 spans four Monday-weeks; A sends in two of them.
    tables = _tables([_event("m1", 4, A, C), _event("m2", 5, A, C), _event("m3", 18, A, C)])
    assert _value(ex.MEASURES["E19"](tables, WINDOW), A) == 0.5


def test_top_sender_share_and_external_share() -> None:
    rows = [
        _event(f"m{i}", 4 + i % 5, s, A, sender_internal=s != D)
        for i, s in enumerate([C, C, C, B, B, D, D, D])
    ]
    rows.append(_event("m9", 9, "p_eeeeeeeeeeeeeeee", A))
    tables = _tables(rows)
    # Top three senders (C, D, B) account for 8 of 9 received messages.
    assert np.isclose(_value(ex.MEASURES["E17"](tables, WINDOW), A), 8 / 9)
    assert np.isclose(_value(ex.MEASURES["E18"](tables, WINDOW), A), 3 / 9)
    assert np.isclose(_value(ex.MEASURES["E14"](tables, WINDOW), A), 2 / 9)  # B is a custodian


def test_sent_shares_for_custodian_list_and_direct_mail() -> None:
    tables = _tables(
        [
            _event("m1", 4, A, B, n=1),  # to a custodian, direct
            _event("m2", 5, A, C, n=2),
            _event("m2", 5, A, L, n=2, rtype="list"),
            _event("m3", 6, A, C, n=1),
            _event("m4", 7, A, A, n=1),  # to self: not a custodian hit
        ]
    )
    assert _value(ex.MEASURES["E13"](tables, WINDOW), A) == 0.25
    assert _value(ex.MEASURES["E20"](tables, WINDOW), A) == 0.25
    assert _value(ex.MEASURES["E11"](tables, WINDOW), A) == 0.75


def test_decision_rule_requires_every_condition() -> None:
    up = ex.Comparison(n=30, median=0.2, ci_low=0.1, ci_high=0.3, p=0.001)
    flat_placebo = ex.Comparison(n=20, median=0.01, ci_low=-0.05, ci_high=0.06, p=0.5)
    trend_placebo = ex.Comparison(n=20, median=0.19, ci_low=0.1, ci_high=0.3, p=0.001)
    assert ex._placebo_passes(ex.UP, up, flat_placebo)
    assert not ex._placebo_passes(ex.UP, up, trend_placebo)
    assert ex._loo_stable(ex.UP, np.array([0.1, 0.2, 0.3, 0.2]))
    assert not ex._loo_stable(ex.UP, np.array([-0.1, 0.2, -0.3, 0.2]))
