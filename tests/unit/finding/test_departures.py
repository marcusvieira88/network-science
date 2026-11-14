"""H26 custodian departures (finding/departures.py) on synthetic worlds with known answers."""

from __future__ import annotations

import base64
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from enron_case.config import CRISIS_SPLIT, CRISIS_WINDOW, Config
from enron_case.contracts import schemas
from enron_case.finding import departures as dep

CONFIG = Config()
START = date(1999, 6, 7)  # a Monday, well before the first look-back
END = date(2002, 12, 23)
N_CUSTODIANS = 40
# Mondays inside the crisis window (2001-08-14 to 2001-12-02).
CRISIS_MONDAYS = tuple(date(2001, 8, 20) + timedelta(weeks=w) for w in range(0, 14, 1))


def pid(kind: str, number: int) -> str:
    """A pseudonym-shaped id: p_ and 16 base32 characters."""
    raw = base64.b32encode(f"{kind}{number:09d}".encode()).decode().lower()
    return "p_" + raw.replace("=", "")[:16].translate(str.maketrans("0189", "abcd"))


CUSTODIANS = tuple(pid("c", n) for n in range(N_CUSTODIANS))
EXTERNALS = tuple(pid("e", n) for n in range(N_CUSTODIANS))
COLLEAGUES = tuple(pid("i", n) for n in range(N_CUSTODIANS))


def mondays(first: date = START, last: date = END) -> list[date]:
    weeks = (last - first).days // 7
    return [first + timedelta(weeks=w) for w in range(weeks + 1)]


def entities(extra_internal: tuple[str, ...] = ()) -> pl.DataFrame:
    rows = [(p, True, True) for p in CUSTODIANS]
    rows += [(p, False, False) for p in EXTERNALS]
    rows += [(p, True, False) for p in (*COLLEAGUES, *extra_internal)]
    return pl.DataFrame(
        {
            "pid": [r[0] for r in rows],
            "type": ["person"] * len(rows),
            "is_internal": [r[1] for r in rows],
            "is_custodian": [r[2] for r in rows],
        }
    )


def world(
    stop_sending: dict[int, date] | None = None,
    stop_receiving: dict[int, date] | None = None,
) -> pl.DataFrame:
    """Every custodian writes weekly to the next custodian and to a colleague, and receives
    weekly mail from an outsider that only their own mailbox holds, until their stop dates."""
    stop_sending = stop_sending or {}
    stop_receiving = stop_receiving or {}
    rows: list[tuple[str, datetime, str, str]] = []
    for week in mondays():
        stamp = datetime(week.year, week.month, week.day, 15, tzinfo=UTC) + timedelta(days=1)
        for n, custodian in enumerate(CUSTODIANS):
            if week < stop_sending.get(n, date.max):
                peer = CUSTODIANS[(n + 1) % N_CUSTODIANS]
                rows.append((f"s{n}-{week}", stamp, custodian, peer))
                rows.append((f"s{n}-{week}", stamp, custodian, COLLEAGUES[n]))
            if week < stop_receiving.get(n, date.max):
                rows.append((f"r{n}-{week}", stamp, EXTERNALS[n], custodian))
    return pl.DataFrame(
        rows,
        schema={
            "msg_pid": pl.String,
            "ts_hour": pl.Datetime("us", "UTC"),
            "sender_pid": pl.String,
            "recipient_pid": pl.String,
        },
        orient="row",
    )


TRICKLE_FIRST = date(2000, 2, 7)
TRICKLE_WEEKS = 10


def background() -> dict[int, date]:
    """A steady trickle: one custodian stops sending every ten weeks, from February 2000 to
    March 2002 (two of them in the crisis window and two in the reference window)."""
    stops = [TRICKLE_FIRST + timedelta(weeks=TRICKLE_WEEKS * j) for j in range(12)]
    return {28 + j: day for j, day in enumerate(stops)}


def crisis_trickle() -> list[date]:
    return [d for d in background().values() if CRISIS_MONDAYS[0] <= d <= CRISIS_WINDOW[1]]


def variant_row(result: dep.Result, variant: str = dep.PRIMARY) -> dict[str, object]:
    return result.tests.filter(pl.col("variant") == variant).row(0, named=True)


def period(result: dep.Result, name: str) -> dict[str, object]:
    return result.periods.filter(pl.col("period") == name).row(0, named=True)


def run_world(events: pl.DataFrame, config: Config = CONFIG) -> dep.Result:
    return dep.departure_tables(events, entities(), config)


# ---- known answers ---------------------------------------------------------------------------
PLANTED = {n: CRISIS_MONDAYS[n] for n in range(10)}


@pytest.fixture(scope="module")
def planted() -> dep.Result:
    return run_world(world(stop_sending=background() | PLANTED))


def test_a_planted_wave_of_departures_is_counted_exactly(planted: dep.Result) -> None:
    crisis = period(planted, dep.CRISIS)
    assert len(crisis_trickle()) == 2
    assert crisis["departures"] == len(PLANTED) + len(crisis_trickle())
    assert crisis["record_ends"] == 0


def test_a_planted_wave_is_detected_with_high_confidence(planted: dep.Result) -> None:
    primary = variant_row(planted)
    assert primary["p_band"] == dep.FAMILY_BOUND
    assert primary["above_rolling"] is True
    assert primary["placebo_p_band"] == dep.ALPHA_OR_ABOVE
    assert primary["loo_stable"] is True
    assert primary["outcome"] == dep.HIGH


def test_the_crisis_split_divides_the_planted_departures(planted: dep.Result) -> None:
    stops = [*PLANTED.values(), *crisis_trickle()]
    before = sum(1 for day in stops if day < CRISIS_SPLIT)  # Monday on or before Oct 15
    assert period(planted, dep.SPLIT_BEFORE)["departures"] == before
    assert period(planted, dep.SPLIT_FROM)["departures"] == len(stops) - before


def test_no_change_world_does_not_fire() -> None:
    result = run_world(world(stop_sending=background()))
    primary = variant_row(result)
    assert primary["outcome"] == dep.NOT_ESTABLISHED
    assert primary["p_band"] == dep.ALPHA_OR_ABOVE


def test_collection_end_is_a_record_end_not_a_departure() -> None:
    """Mailboxes that stop holding any mail in the crisis are the artifact, not departures."""
    ends = {n: CRISIS_MONDAYS[n] for n in range(10)}
    result = run_world(world(stop_sending=background() | ends, stop_receiving=ends))
    crisis = period(result, dep.CRISIS)
    assert crisis["departures"] == len(crisis_trickle())  # only the steady trickle
    assert crisis["record_ends"] == len(ends)
    assert variant_row(result)["outcome"] == dep.NOT_ESTABLISHED
    assert variant_row(result, "any silence")["p_band"] == dep.FAMILY_BOUND


def test_a_wave_already_in_the_placebo_months_blocks_the_finding() -> None:
    """The same wave in early 2001 and again in the crisis: a pre-existing trend."""
    early = {n + 10: day - timedelta(weeks=30) for n, day in PLANTED.items()}
    result = run_world(world(stop_sending=background() | PLANTED | early))
    primary = variant_row(result)
    assert primary["placebo_p_band"] != dep.ALPHA_OR_ABOVE
    assert primary["outcome"] == dep.NOT_ESTABLISHED


def outcome_of(at_risk: int, departed: int) -> dep.Outcome:
    flags = np.arange(N_CUSTODIANS)
    return dep.Outcome(
        at_risk=flags < at_risk,
        departed=flags < departed,
        record_end=np.zeros(N_CUSTODIANS, dtype=np.bool_),
        departure_week=np.full(N_CUSTODIANS, dep.NO_WEEK, dtype=np.int64),
    )


@pytest.mark.parametrize(
    ("rolling", "above", "counted"),
    [
        ((outcome_of(40, 4), outcome_of(40, 6)), True, 2),
        ((outcome_of(40, 4), outcome_of(40, 9)), False, 2),  # an earlier window as high
        ((outcome_of(40, 4), outcome_of(10, 9)), True, 1),  # too few at risk to count
        ((outcome_of(10, 9),), False, 0),  # nothing to compare with: not above
    ],
)
def test_rolling_comparison(rolling: tuple[dep.Outcome, ...], above: bool, counted: int) -> None:
    evaluation = dep.Evaluation(
        variant=dep.variants(CONFIG)[0],
        crisis=outcome_of(40, 8),
        reference=outcome_of(40, 2),
        placebo_after=outcome_of(40, 2),
        placebo_before=outcome_of(40, 2),
        rolling=rolling,
    )
    result = dep.summarise(evaluation, np.ones(N_CUSTODIANS, dtype=np.bool_), CONFIG)
    assert result.above_rolling is above
    assert result.rolling_windows == counted


def test_a_new_pseudonym_writing_to_the_same_people_is_successor_like() -> None:
    """Custodian 0 goes quiet and a pseudonym silent until then writes to both its contacts."""
    config = replace(CONFIG, successor_min_shared=2)  # each world custodian has two contacts
    heir = pid("h", 0)
    events = world(stop_sending=background() | PLANTED)
    stamps = [datetime(d.year, d.month, d.day, 15, tzinfo=UTC) for d in mondays(PLANTED[0], END)]
    extra = pl.DataFrame(
        [(f"h-{t}", t, heir, to) for t in stamps for to in (CUSTODIANS[1], COLLEAGUES[0])],
        schema=events.schema,
        orient="row",
    )
    events, people = pl.concat([events, extra]), entities((heir,))
    record = dep.build_record(events, people, config)
    candidates = dep.successor_candidates(record, dep.variants(config)[0])
    flagged = dep.successor_matrix(record, events, people, candidates, config)
    assert int(flagged.sum()) == 1
    assert flagged[0, record.column(PLANTED[0])]
    no_successor = next(v for v in dep.variants(config) if v.drop_successors)
    crisis = dep.evaluate(record, no_successor, flagged).crisis
    assert int(crisis.departed.sum()) == len(PLANTED) + len(crisis_trickle()) - 1


def test_custodian_visible_variant_reads_only_mail_to_other_custodians() -> None:
    """Custodian 0 stops writing to custodians in the crisis but keeps writing to a colleague:
    not a departure for the primary definition, a departure for the custodian-visible one."""
    events = world(stop_sending=background()).filter(
        ~(
            (pl.col("sender_pid") == CUSTODIANS[0])
            & (pl.col("recipient_pid") == CUSTODIANS[1])
            & (pl.col("ts_hour").dt.date() >= PLANTED[0])
        )
    )
    record = dep.build_record(events, entities(), CONFIG)
    primary, visible = dep.variants(CONFIG)[0], dep.variants(CONFIG)[7]
    no_successors = np.zeros_like(record.sent)
    assert not dep.evaluate(record, primary, no_successors).crisis.departed[0]
    assert dep.evaluate(record, visible, no_successors).crisis.departed[0]


# ---- definitions on small cases --------------------------------------------------------------
def tiny_record(sent: list[int], mailbox: list[int]) -> dep.Record:
    return dep.Record(
        custodians=(CUSTODIANS[0],),
        first_week=START,
        sent=np.array([sent], dtype=np.bool_),
        sent_to_custodian=np.array([sent], dtype=np.bool_),
        mailbox=np.array([mailbox], dtype=np.bool_),
    )


SMALL = dep.Variant("small", silence_weeks=3, live_weeks=2, active_weeks=2, lookback_weeks=4)


def test_a_silence_starts_after_the_last_sent_week_and_must_fit_in_the_record() -> None:
    record = tiny_record([1, 1, 1, 0, 0, 0, 1, 0, 0], [1, 1, 1, 1, 1, 0, 0, 0, 0])
    found = dep.silences(record, SMALL)
    assert found.starts[0].tolist() == [
        False,
        False,
        False,
        True,
        False,
        False,
        False,
        False,
        False,
    ]  # weeks 7-9 are quiet but run past the record
    assert found.live[0, 3]  # mailbox mail in two of weeks 3-5


def test_a_silence_without_mail_arriving_is_not_live() -> None:
    record = tiny_record([1, 1, 1, 0, 0, 0, 1], [1, 1, 1, 1, 0, 0, 0])
    found = dep.silences(record, SMALL)
    assert found.starts[0, 3] and not found.live[0, 3]


def test_at_risk_needs_both_sides_covered_in_the_lookback() -> None:
    covered = tiny_record([1, 1, 0, 1, 0], [1, 0, 1, 0, 0])
    sent_only = tiny_record([1, 1, 0, 1, 0], [0, 0, 0, 1, 0])
    for record, expected in ((covered, True), (sent_only, False)):
        found = dep.silences(record, SMALL)
        assert bool(dep.at_risk(record, SMALL, found, 4)[0]) is expected


def test_record_columns_cover_mondays_inside_the_window() -> None:
    record = tiny_record([0], [0])
    first, last = record.columns(CRISIS_WINDOW)
    assert record.monday(first) == date(2001, 8, 20)
    assert record.monday(last) == date(2001, 11, 26)


def test_rolling_windows_have_the_crisis_length_and_end_before_it() -> None:
    windows = dep.rolling_windows()
    assert windows[0][0] == date(2000, 1, 3)
    assert all(end - start == CRISIS_WINDOW[1] - CRISIS_WINDOW[0] for start, end in windows)
    assert windows[-1][1] < CRISIS_WINDOW[0] <= windows[-1][1] + timedelta(weeks=1)


def test_mailbox_only_mail_excludes_copies_another_custodian_could_hold() -> None:
    stamp = datetime(2000, 3, 7, 15, tzinfo=UTC)
    events = pl.DataFrame(
        {
            "msg_pid": ["m1", "m1", "m2", "m3"],
            "ts_hour": [stamp] * 4,
            "sender_pid": [EXTERNALS[0], EXTERNALS[0], CUSTODIANS[2], EXTERNALS[1]],
            "recipient_pid": [CUSTODIANS[0], CUSTODIANS[1], CUSTODIANS[0], CUSTODIANS[1]],
        }
    )
    record = dep.build_record(events, entities(), CONFIG)
    assert record.mailbox[0].sum() == 0  # m1 is also in custodian 1's mailbox; m2 from one
    assert record.mailbox[1].sum() == 1  # m3 only


# ---- tests and the decision rule -------------------------------------------------------------
def test_fisher_p_is_one_sided_with_known_value() -> None:
    later, earlier = dep.Tally(10, 5, 0), dep.Tally(10, 0, 0)
    # Hypergeometric tail: C(10,5)C(10,0)/C(20,5) = 252/15504.
    assert dep.one_sided_p(later, earlier) == pytest.approx(252 / 15504)
    assert dep.one_sided_p(earlier, later) == pytest.approx(1.0)
    assert np.isnan(dep.one_sided_p(dep.Tally(0, 0, 0), earlier))


@pytest.mark.parametrize(
    ("p", "band"),
    [
        (0.001, dep.FAMILY_BOUND),
        (0.01, dep.BELOW_ALPHA),
        (0.05, dep.ALPHA_OR_ABOVE),
        (float("nan"), dep.NOT_COMPUTABLE),
    ],
)
def test_p_bands(p: float, band: str) -> None:
    assert dep.p_band(p, CONFIG) == band


def summary(
    p: float = 0.001,
    above: bool = True,
    placebo_p: float = 0.5,
    departures: int = 8,
    reference: int = 1,
) -> dep.Summary:
    return dep.Summary(
        crisis=dep.Tally(50, departures, 0),
        reference=dep.Tally(50, reference, 0),
        placebo_after=dep.Tally(30, 1, 0),
        placebo_before=dep.Tally(30, 1, 0),
        p=p,
        placebo_p=placebo_p,
        rolling_windows=40,
        above_rolling=above,
    )


VARIANT = dep.variants(CONFIG)[1]
OUT_OF_RULE = replace(VARIANT, in_rule=False)


@pytest.mark.parametrize(
    ("primary", "others", "loo", "expected"),
    [
        (summary(), [(VARIANT, summary())], True, dep.HIGH),
        (summary(p=0.01), [(VARIANT, summary())], True, dep.MODERATE),
        (summary(), [(VARIANT, summary(p=0.2))], True, dep.MODERATE),
        (summary(), [(VARIANT, summary(departures=1, reference=2))], True, dep.LOW),
        (summary(), [(OUT_OF_RULE, summary(departures=1, reference=2))], True, dep.HIGH),
        (summary(), [(VARIANT, summary())], False, dep.LOW),
        (summary(departures=4), [(VARIANT, summary())], True, dep.NOT_ESTABLISHED),
        (summary(above=False), [(VARIANT, summary())], True, dep.NOT_ESTABLISHED),
        (summary(placebo_p=0.01), [(VARIANT, summary())], True, dep.NOT_ESTABLISHED),
        (summary(placebo_p=float("nan")), [(VARIANT, summary())], True, dep.NOT_ESTABLISHED),
        (summary(p=0.06), [(VARIANT, summary())], True, dep.NOT_ESTABLISHED),
    ],
)
def test_decision_rule(
    primary: dep.Summary,
    others: list[tuple[dep.Variant, dep.Summary]],
    loo: bool,
    expected: str,
) -> None:
    assert dep.decide(primary, others, loo, CONFIG) == expected


def test_variants_are_the_ones_stated_before_computing() -> None:
    names = [v.name for v in dep.variants(CONFIG)]
    assert names == [
        "primary",
        "silence 8",
        "silence 26",
        "live 1",
        "live 8",
        "active 2",
        "active 8",
        "custodian-visible",
        "same cohort",
        "no successor",
        "any silence",
    ]


def test_tables_match_their_contracts(planted: dep.Result) -> None:
    schemas.validate(planted.periods, "departure_results")
    schemas.validate(planted.tests, "departure_test_results")
