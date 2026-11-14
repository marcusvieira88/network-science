"""Exploratory measures (finding/exploratory.py) on hand-built events with known answers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from enron_case.config import (
    CRISIS_WINDOW,
    PLACEBO_AFTER_WINDOW,
    PLACEBO_BEFORE_WINDOW,
    REFERENCE_WINDOW,
    Config,
)
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


def test_reciprocity_counts_contacts_who_also_wrote_to_the_custodian() -> None:
    tables = _tables(
        [
            _event("m1", 4, A, C),
            _event("m2", 5, A, D),  # A writes to C and D
            _event("m3", 6, C, A),  # only C writes to A (anything, not necessarily a reply)
        ]
    )
    assert _value(ex.MEASURES["H16"](tables, WINDOW), A) == 0.5


def test_reciprocity_description_does_not_claim_a_reply() -> None:
    h16 = next(h for h in ex.FAMILY if h.id == "H16")
    assert h16.description == "share of sent-to contacts who also wrote to the custodian"


def test_new_contact_share_uses_the_lookback() -> None:
    tables = _tables(
        [
            _event("m0", 10, A, C, month=7),  # C known from July
            _event("m1", 4, A, C),
            _event("m2", 5, A, D),  # D is new in the window
        ]
    )
    assert _value(ex.MEASURES["H19"](tables, WINDOW), A) == 0.5


def test_new_contact_share_needs_a_history() -> None:
    tables = _tables([_event("m1", 4, A, C)])
    assert ex.MEASURES["H19"](tables, WINDOW).filter(pl.col("pid") == A).is_empty()


def test_active_week_share() -> None:
    # Window 2001-09-03 .. 2001-09-30 spans four Monday-weeks; A sends in two of them.
    tables = _tables([_event("m1", 4, A, C), _event("m2", 5, A, C), _event("m3", 18, A, C)])
    assert _value(ex.MEASURES["H23"](tables, WINDOW), A) == 0.5


def test_top_sender_share_and_external_share() -> None:
    rows = [
        _event(f"m{i}", 4 + i % 5, s, A, sender_internal=s != D)
        for i, s in enumerate([C, C, C, B, B, D, D, D])
    ]
    rows.append(_event("m9", 9, "p_eeeeeeeeeeeeeeee", A))
    tables = _tables(rows)
    # Top three senders (C, D, B) account for 8 of 9 received messages.
    assert np.isclose(_value(ex.MEASURES["H21"](tables, WINDOW), A), 8 / 9)
    assert np.isclose(_value(ex.MEASURES["H22"](tables, WINDOW), A), 3 / 9)
    assert np.isclose(_value(ex.MEASURES["H18"](tables, WINDOW), A), 2 / 9)  # B is a custodian


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
    assert _value(ex.MEASURES["H17"](tables, WINDOW), A) == 0.25
    assert _value(ex.MEASURES["H24"](tables, WINDOW), A) == 0.25
    assert _value(ex.MEASURES["H15"](tables, WINDOW), A) == 0.75


def test_decision_rule_requires_every_condition() -> None:
    up = ex.Comparison(n=30, median=0.2, ci_low=0.1, ci_high=0.3, p=0.001)
    flat_placebo = ex.Comparison(n=20, median=0.01, ci_low=-0.05, ci_high=0.06, p=0.5)
    trend_placebo = ex.Comparison(n=20, median=0.19, ci_low=0.1, ci_high=0.3, p=0.001)
    assert ex._placebo_passes(ex.UP, up, flat_placebo)
    assert not ex._placebo_passes(ex.UP, up, trend_placebo)
    assert ex._loo_stable(ex.UP, np.array([0.1, 0.2, 0.3, 0.2]))
    assert not ex._loo_stable(ex.UP, np.array([-0.1, 0.2, -0.3, 0.2]))


def test_flat_placebo_passes() -> None:
    flat = ex.compare(np.zeros(12), Config(), 0)
    assert (flat.median, flat.ci_low, flat.ci_high) == (0.0, 0.0, 0.0)
    up = ex.Comparison(n=30, median=0.2, ci_low=0.1, ci_high=0.3, p=0.001)
    assert ex._placebo_passes(ex.UP, up, flat)


def test_daylight_saving_uses_the_real_switch_dates() -> None:
    rows = pl.DataFrame(
        {
            "ts_hour": [
                datetime(2001, 10, 28, 6, tzinfo=UTC),  # before 07:00 UTC switch: CDT, UTC-5
                datetime(2001, 10, 29, 13, tzinfo=UTC),  # after the switch: CST, UTC-6
                datetime(2001, 4, 1, 9, tzinfo=UTC),  # after the 08:00 UTC spring switch
            ]
        }
    )
    hours = ex._with_local_time(rows).get_column("hour").to_list()
    assert hours == [1, 7, 4]


def test_active_weeks_count_full_weeks_only() -> None:
    # Window Tue 2001-08-14 .. Sun 2001-12-02: full weeks start Mon 2001-08-20; 15 full weeks.
    window = (date(2001, 8, 14), date(2001, 12, 2))
    rows = [_event(f"m{i}", 1, A, C, month=9) for i in range(3)]
    rows.append(_event("edge", 14, A, C, month=8))  # Tuesday in a partial week: not counted
    value = _value(ex.MEASURES["H23"](_tables(rows), window), A)
    assert np.isclose(value, 1 / 15)


def test_after_hours_share_ignores_weekend_volume() -> None:
    # Two weekday messages (one after hours) plus weekend mail: share stays 1/2.
    rows = [
        {**_event("m1", 3, A, C), "ts_hour": datetime(2001, 9, 3, 23, tzinfo=UTC)},  # 18:00
        {**_event("m2", 4, A, C), "ts_hour": datetime(2001, 9, 5, 2, tzinfo=UTC)},  # 21:00
        {**_event("m3", 8, A, C), "ts_hour": datetime(2001, 9, 8, 17, tzinfo=UTC)},  # Saturday
    ]
    assert _value(ex.MEASURES["H5"](_tables(rows), WINDOW), A) == 0.5


def _family_events(planted: bool) -> pl.DataFrame:
    """Twenty custodians (fewer cannot reach Holm significance across 20 tests with a
    Wilcoxon test), 30 sent messages per window. In the crisis window (if planted) every
    custodian sends 60 % direct (one-recipient) mail against 20 % in every other window."""
    custodians = [f"p_{chr(97 + i) * 16}" for i in range(20)]
    rows = []
    windows = {
        "crisis": CRISIS_WINDOW,
        "reference": REFERENCE_WINDOW,
        "p1": PLACEBO_AFTER_WINDOW,
        "p0": PLACEBO_BEFORE_WINDOW,
    }
    for name, (start, _end) in windows.items():
        direct = 18 if (planted and name == "crisis") else 6
        for c_index, sender in enumerate(custodians):
            for k in range(30):
                monday = start + timedelta(days=(7 - start.weekday()) % 7 + 7)
                day = monday + timedelta(days=7 * (k // 5) + k % 5)  # weekdays only
                n = 1 if k < direct + c_index % 2 else 2
                ts = datetime(day.year, day.month, day.day, 16, tzinfo=UTC)
                for r in range(n):
                    rows.append(
                        {
                            "msg_pid": f"{name}-{sender}-{k}",
                            "ts_hour": ts,
                            "sender_pid": sender,
                            "recipient_pid": f"p_{'z' * 15}{r}",
                            "role": "to",
                            "n_recipients": n,
                            "recipient_type": "person",
                            "recipient_internal": True,
                            "sender_internal": True,
                        }
                    )
    return pl.DataFrame(rows)


def _entities(events: pl.DataFrame) -> pl.DataFrame:
    senders = events.get_column("sender_pid").unique().sort()
    return pl.DataFrame(
        {"pid": senders, "type": "person", "is_internal": True, "is_custodian": True}
    )


def test_family_finds_a_planted_change_and_nothing_else() -> None:
    events = _family_events(planted=True)
    table = ex.run_family(events, _entities(events), Config(exploratory_bootstrap_reps=500))
    assert table.height == len(ex.FAMILY)
    e11 = table.filter(pl.col("hypothesis") == "H15").row(0, named=True)
    assert e11["outcome"] == ex.CONFIDENT
    assert e11["placebo_passes"] and e11["loo_stable"]
    # Family-adjusted equalised p: p times the family size, capped at 1.
    assert e11["equalised_p_holm"] == pytest.approx(min(1.0, len(ex.FAMILY) * e11["equalised_p"]))
    assert table.filter(pl.col("equalised_p").is_null())["equalised_p_holm"].null_count() == (
        table.filter(pl.col("equalised_p").is_null()).height
    )
    flat = ex.run_family(
        _family_events(planted=False), _entities(events), Config(exploratory_bootstrap_reps=500)
    )
    assert ex.CONFIDENT not in flat.get_column("outcome").to_list()


def test_caveated_hypotheses_are_never_confident() -> None:
    assert set(ex.CAVEATS) == {"H5", "H7", "H19"}


def test_subsample_caps_each_custodian_and_ignores_row_order() -> None:
    rows = pl.DataFrame({"pid": [A] * 6 + [B] * 4, "msg_pid": [f"m{i}" for i in range(10)]})
    caps = pl.DataFrame({"pid": [A, B], "cap": [2, 3]})
    first = ex._subsample(rows, caps, "cap", seed=11)
    again = ex._subsample(rows.sample(fraction=1.0, shuffle=True, seed=5), caps, "cap", seed=11)
    assert first.group_by("pid").len().sort("pid").get_column("len").to_list() == [2, 3]
    assert first.sort("msg_pid").equals(again.sort("msg_pid"))


def test_volume_equalised_with_too_few_custodians_is_not_computed() -> None:
    events = _family_events(planted=True).filter(
        pl.col("sender_pid").is_in([f"p_{chr(97 + i) * 16}" for i in range(3)])
    )
    tables = ex.Tables(
        ex.sent_messages(events, events.get_column("sender_pid").unique()),
        ex.received_messages(events, events.get_column("sender_pid").unique()),
    )
    result = ex.volume_equalised(
        tables, ex.MEASURES["H15"], CRISIS_WINDOW, REFERENCE_WINDOW, Config(), stream=0
    )
    assert result.n < Config().k_min
    assert np.isnan(result.median)


def test_reciprocity_between_custodians_ignores_non_custodian_contacts() -> None:
    rows = [
        _event("m1", 4, A, B),  # to custodian B
        _event("m2", 5, A, C),  # to non-custodian C
        _event("m3", 6, C, A),  # C writes to A: does not count here
    ]
    events = pl.DataFrame(rows)
    tables = ex.Tables(
        ex.sent_messages(events, CUSTODIANS),
        ex.received_messages(events, CUSTODIANS),
        frozenset(CUSTODIANS.to_list()),
    )
    result = ex._reciprocity_between_custodians(tables, WINDOW)
    assert _value(result, A) == 0.0  # B did not write to A
    assert (
        int(result.filter(pl.col("pid") == A).get_column("n").item()) == 1
    )  # min(sent 2, received 1)


def test_a_failed_retention_check_caps_the_outcome() -> None:
    """A planted crisis rise in direct mail (H15) that a retention measure contradicts must not be
    held true: the check fails and the outcome becomes inconclusive with the caveat."""
    events = _family_events(planted=True)
    flat = ex.MEASURES["H6"]
    checks = dict(ex.RETENTION_CHECKS)
    ex.RETENTION_CHECKS.clear()
    # Weekend share: flat in this world, so the check fails.
    ex.RETENTION_CHECKS["H15"] = ex.RetentionRule(flat, "planted caveat")
    try:
        table = ex.run_family(events, _entities(events), Config(exploratory_bootstrap_reps=500))
    finally:
        ex.RETENTION_CHECKS.clear()
        ex.RETENTION_CHECKS.update(checks)
    h15 = table.filter(pl.col("hypothesis") == "H15").row(0, named=True)
    assert h15["retention_passes"] is False
    assert h15["outcome"] == ex.INCONCLUSIVE
    assert h15["caveat"] == "planted caveat"


THREE_CUSTODIANS = pl.Series([A, B, D])


def _three_custodian_tables(rows: list[dict[str, object]]) -> ex.Tables:
    events = pl.DataFrame(rows)
    return ex.Tables(
        ex.sent_messages(events, THREE_CUSTODIANS),
        ex.received_messages(events, THREE_CUSTODIANS),
        frozenset(THREE_CUSTODIANS.to_list()),
    )


def test_core_ego_density_counts_custodians_in_either_direction() -> None:
    """H25: A wrote to custodian B, custodian D wrote to A, A wrote to non-custodian C. A is in
    contact with both other custodians (2 of 2); B and D each with one of two."""
    tables = _three_custodian_tables(
        [_event("m1", 4, A, B), _event("m2", 5, D, A), _event("m3", 6, A, C)]
    )
    result = ex._core_ego_density(tables, WINDOW)
    assert _value(result, A) == pytest.approx(1.0)
    assert _value(result, B) == pytest.approx(0.5)
    assert _value(result, D) == pytest.approx(0.5)
    n = dict(result.select("pid", "n").iter_rows())
    assert n == {A: 1, B: 0, D: 0}  # min(sent, received): A sent 2, received 1


def test_core_out_density_ignores_every_inbox() -> None:
    """The H25 retention measure counts only the custodians written to: A wrote to B only."""
    tables = _three_custodian_tables(
        [_event("m1", 4, A, B), _event("m2", 5, D, A), _event("m3", 6, A, C)]
    )
    result = ex._core_out_density(tables, WINDOW)
    assert _value(result, A) == pytest.approx(0.5)
    assert _value(result, B) == pytest.approx(0.0)  # B received but wrote to no custodian
    assert _value(result, D) == pytest.approx(0.5)


def test_h25_is_post_hoc_and_has_a_retention_check() -> None:
    h25 = [h for h in ex.FAMILY if h.id == "H25"]
    assert len(h25) == 1 and h25[0].direction == ex.UP
    assert set(ex.RETENTION_CHECKS) == {"H16", "H25"}
    assert ex.family_of(len(ex.FAMILY) - 1) == ex.POST_HOC_FAMILY
    assert ex.family_of(0) == ex.FIRST_FAMILY
