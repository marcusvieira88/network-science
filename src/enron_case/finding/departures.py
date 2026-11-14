"""H26 (O1 in docs/hypotheses-exploratory.md, post hoc): did custodians leave in the crisis?

A departure is a custodian who stops sending for a whole silence while their own mailbox keeps
receiving mail that only it can hold. That separates "stopped sending" from "mailbox not
collected" (a record end: mail stops arriving too). Everything is read at week resolution from
presence of mail, never from hours or volumes, so neither the change of the `Date` convention
nor the growth of the inbox mail kept moves it except through the stated "live" threshold,
which a variant tests.

The departure share in the crisis window is compared with the same weeks a year earlier
(one-sided Fisher exact test), with a pre-crisis placebo, with every earlier window of the same
length (rolling placebo), leaving each custodian out in turn, and under the variants stated
before computing. The decision rule turns these into an outcome.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta

import numpy as np
import numpy.typing as npt
import polars as pl
from scipy.stats import fisher_exact

from enron_case.config import (
    CRISIS_SPLIT,
    CRISIS_WINDOW,
    HYPOTHESES_STATED,
    PLACEBO_AFTER_WINDOW,
    PLACEBO_BEFORE_WINDOW,
    REFERENCE_WINDOW,
    Config,
)
from enron_case.contracts import schemas, vocab

Bools = npt.NDArray[np.bool_]
Ints = npt.NDArray[np.int64]
Window = tuple[date, date]

DAYS_PER_WEEK = 7
NO_WEEK = -1  # departure week of a custodian who did not depart
PRIMARY = schemas.DEPARTURE_PRIMARY
HIGH, MODERATE, LOW, NOT_ESTABLISHED = schemas.DEPARTURE_OUTCOMES
FAMILY_BOUND, BELOW_ALPHA, ALPHA_OR_ABOVE, NOT_COMPUTABLE = schemas.P_BANDS
CRISIS, REFERENCE, PLACEBO_AFTER, PLACEBO_BEFORE, SPLIT_BEFORE, SPLIT_FROM = (
    schemas.DEPARTURE_PERIODS
)


# ---- the record: one row per custodian, one column per week ---------------------------------
@dataclass(frozen=True)
class Record:
    """Which weeks each custodian sent mail in, sent mail to another custodian in, and received
    mail that only their own mailbox can hold (mailbox-only weeks)."""

    custodians: tuple[str, ...]
    first_week: date  # Monday of column 0
    sent: Bools
    sent_to_custodian: Bools
    mailbox: Bools

    @property
    def weeks(self) -> int:
        return int(self.sent.shape[1])

    def column(self, day: date) -> int:
        """Column of the week holding `day`."""
        return (day - self.first_week).days // DAYS_PER_WEEK

    def columns(self, window: Window) -> tuple[int, int]:
        """First and last column whose Monday lies in the window (inclusive)."""
        first = -(-(window[0] - self.first_week).days // DAYS_PER_WEEK)
        return first, self.column(window[1])

    def monday(self, column: int) -> date:
        return self.first_week + timedelta(weeks=column)


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _week_column(first_week: date) -> pl.Expr:
    monday = pl.col("ts_hour").dt.truncate("1w").dt.date()
    return ((monday - pl.lit(first_week)).dt.total_days() // DAYS_PER_WEEK).alias("column")


def _matrix(pairs: pl.DataFrame, pid_column: str, index: dict[str, int], weeks: int) -> Bools:
    """Boolean custodian-by-week matrix from rows holding a custodian pid and a week column."""
    matrix = np.zeros((len(index), weeks), dtype=np.bool_)
    rows = np.array([index[pid] for pid in pairs.get_column(pid_column).to_list()], dtype=np.int64)
    cols = pairs.get_column("column").to_numpy().astype(np.int64)
    matrix[rows, cols] = True
    return matrix


def build_record(events: pl.DataFrame, entities_p: pl.DataFrame, config: Config) -> Record:
    """The record of every custodian over the plausible date range."""
    custodians = tuple(
        sorted(entities_p.filter(pl.col("is_custodian")).get_column("pid").to_list())
    )
    index = {pid: row for row, pid in enumerate(custodians)}
    first_week = monday_of(config.plausible_start)
    weeks = (config.plausible_end - first_week).days // DAYS_PER_WEEK + 1
    day = pl.col("ts_hour").dt.date()
    dated = events.filter(day.is_between(config.plausible_start, config.plausible_end))
    dated = dated.with_columns(_week_column(first_week))
    is_custodian = pl.col("sender_pid").is_in(list(custodians))
    sent = dated.filter(is_custodian).select("sender_pid", "column").unique()
    to_custodian = (
        dated.filter(
            is_custodian
            & pl.col("recipient_pid").is_in(list(custodians))
            & (pl.col("recipient_pid") != pl.col("sender_pid"))
        )
        .select("sender_pid", "column")
        .unique()
    )
    return Record(
        custodians=custodians,
        first_week=first_week,
        sent=_matrix(sent, "sender_pid", index, weeks),
        sent_to_custodian=_matrix(to_custodian, "sender_pid", index, weeks),
        mailbox=_matrix(_mailbox_only(dated, custodians), "recipient_pid", index, weeks),
    )


def _mailbox_only(dated: pl.DataFrame, custodians: tuple[str, ...]) -> pl.DataFrame:
    """Weeks in which a custodian received a message from a non-custodian that no other
    custodian received: such a message can survive only in that custodian's own mailbox."""
    to_custodians = dated.filter(pl.col("recipient_pid").is_in(list(custodians)))
    per_message = to_custodians.group_by("msg_pid").agg(
        pl.col("recipient_pid").n_unique().alias("custodian_recipients"),
        pl.col("recipient_pid").first(),
        pl.col("sender_pid").first(),
        pl.col("column").first(),
    )
    return (
        per_message.filter(
            (pl.col("custodian_recipients") == 1) & ~pl.col("sender_pid").is_in(list(custodians))
        )
        .select("recipient_pid", "column")
        .unique()
    )


# ---- definitions of one variant --------------------------------------------------------------
@dataclass(frozen=True)
class Variant:
    name: str
    silence_weeks: int
    live_weeks: int
    active_weeks: int
    lookback_weeks: int
    custodian_visible: bool = False  # a sent week counts only mail to another custodian
    same_cohort: bool = False  # at risk in W1 (P1) only if also at risk at W0's (P0's) start
    drop_successors: bool = False
    any_silence: bool = False  # every silence counts as a departure, live or not
    in_rule: bool = True


def variants(config: Config) -> tuple[Variant, ...]:
    """The primary definition and the robustness variants stated before computing."""
    primary = Variant(
        PRIMARY,
        config.departure_silence_weeks,
        config.departure_live_weeks,
        config.departure_active_weeks,
        config.departure_lookback_weeks,
    )
    return (
        primary,
        *(
            replace(primary, name=f"silence {s}", silence_weeks=s)
            for s in config.departure_silence_variants
        ),
        *(replace(primary, name=f"live {n}", live_weeks=n) for n in config.departure_live_variants),
        *(
            replace(primary, name=f"active {n}", active_weeks=n)
            for n in config.departure_active_variants
        ),
        replace(primary, name="custodian-visible", custodian_visible=True),
        replace(primary, name="same cohort", same_cohort=True),
        replace(primary, name="no successor", drop_successors=True),
        replace(primary, name="any silence", any_silence=True, in_rule=False),
    )


def _cumulative(matrix: Bools) -> Ints:
    """Row-wise counts of True before each column: out[:, w] = matrix[:, :w].sum(1)."""
    zeros = np.zeros((matrix.shape[0], 1), dtype=np.int64)
    return np.concatenate([zeros, np.cumsum(matrix, axis=1, dtype=np.int64)], axis=1)


def _forward_counts(matrix: Bools, length: int) -> Ints:
    """out[:, w] = True cells in columns w .. w + length - 1; -1 where that runs past the end."""
    weeks = matrix.shape[1]
    cumulative = _cumulative(matrix)
    out = np.full(matrix.shape, -1, dtype=np.int64)
    span = weeks - length + 1
    if span > 0:
        out[:, :span] = cumulative[:, length : length + span] - cumulative[:, :span]
    return out


def _backward_count(matrix: Bools, column: int, length: int) -> Ints:
    """True cells per row in the `length` columns before `column` (fewer at the record start)."""
    return matrix[:, max(column - length, 0) : column].sum(axis=1).astype(np.int64)


@dataclass(frozen=True)
class Silences:
    """Per custodian and week: does a silence start there, and is it live?"""

    starts: Bools
    live: Bools


def silences(record: Record, variant: Variant) -> Silences:
    sent = record.sent_to_custodian if variant.custodian_visible else record.sent
    quiet = _forward_counts(sent, variant.silence_weeks) == 0
    after_sent = np.zeros_like(sent)
    after_sent[:, 1:] = sent[:, :-1]
    starts = after_sent & quiet
    live = _forward_counts(record.mailbox, variant.silence_weeks) >= variant.live_weeks
    return Silences(starts, starts & live)


def at_risk(record: Record, variant: Variant, found: Silences, column: int) -> Bools:
    """Custodians covered on both sides in the look-back and not already silent at `column`."""
    sent = record.sent_to_custodian if variant.custodian_visible else record.sent
    lookback = variant.lookback_weeks
    if column < lookback:
        return np.zeros(len(record.custodians), dtype=np.bool_)
    active = _backward_count(sent, column, lookback) >= variant.active_weeks
    covered = _backward_count(record.mailbox, column, lookback) >= variant.active_weeks
    gone = _backward_count(found.starts, column, lookback) > 0
    return active & covered & ~gone


# ---- one window ------------------------------------------------------------------------------
@dataclass(frozen=True)
class Outcome:
    """Per custodian, for one window: at risk, departed, record end, and the week of the first
    live silence start (NO_WEEK if none)."""

    at_risk: Bools
    departed: Bools
    record_end: Bools
    departure_week: Ints


def window_outcome(
    record: Record,
    variant: Variant,
    found: Silences,
    window: Window,
    successors: Bools,
    cohort_start: date | None = None,
) -> Outcome:
    first, last = record.columns(window)
    risk = at_risk(record, variant, found, first)
    if variant.same_cohort and cohort_start is not None:
        risk = risk & at_risk(
            record, variant, found, record.columns((cohort_start, cohort_start))[0]
        )
    starts = found.starts[:, first : last + 1]
    live = found.live[:, first : last + 1]
    has_start, has_live = starts.any(axis=1), live.any(axis=1)
    departed = risk & (has_start if variant.any_silence else has_live)
    record_end = risk & has_start & ~has_live
    if variant.drop_successors:
        succeeded = (live & successors[:, first : last + 1]).any(axis=1) & departed
        risk, departed = risk & ~succeeded, departed & ~succeeded
    first_live = np.where(has_live, live.argmax(axis=1) + first, NO_WEEK).astype(np.int64)
    return Outcome(risk, departed, record_end, np.where(departed, first_live, NO_WEEK))


@dataclass(frozen=True)
class Tally:
    at_risk: int
    departures: int
    record_ends: int

    @property
    def hazard(self) -> float:
        return self.departures / self.at_risk if self.at_risk else float("nan")


def tally(outcome: Outcome, keep: Bools) -> Tally:
    return Tally(
        int((outcome.at_risk & keep).sum()),
        int((outcome.departed & keep).sum()),
        int((outcome.record_end & keep).sum()),
    )


def one_sided_p(later: Tally, earlier: Tally) -> float:
    """Fisher exact p that the departure share of `later` exceeds that of `earlier`."""
    if not later.at_risk or not earlier.at_risk:
        return float("nan")
    table = [
        [later.departures, later.at_risk - later.departures],
        [earlier.departures, earlier.at_risk - earlier.departures],
    ]
    return float(fisher_exact(table, alternative="greater").pvalue)


def smallest_cell(later: Tally, earlier: Tally) -> int:
    return min(
        later.departures,
        later.at_risk - later.departures,
        earlier.departures,
        earlier.at_risk - earlier.departures,
    )


def first_monday_from(day: date) -> date:
    return day + timedelta(days=(DAYS_PER_WEEK - day.weekday()) % DAYS_PER_WEEK)


def rolling_windows() -> tuple[Window, ...]:
    """Every window of the crisis window's length starting on a Monday from the first Monday of
    2000 whose end lies before the crisis window starts."""
    length = CRISIS_WINDOW[1] - CRISIS_WINDOW[0]
    start = first_monday_from(PLACEBO_BEFORE_WINDOW[0])
    windows = []
    while start + length < CRISIS_WINDOW[0]:
        windows.append((start, start + length))
        start += timedelta(weeks=1)
    return tuple(windows)


# ---- a variant across every window -----------------------------------------------------------
@dataclass(frozen=True)
class Evaluation:
    variant: Variant
    crisis: Outcome
    reference: Outcome
    placebo_after: Outcome
    placebo_before: Outcome
    rolling: tuple[Outcome, ...]


def evaluate(record: Record, variant: Variant, successors: Bools) -> Evaluation:
    found = silences(record, variant)

    def outcome(window: Window, cohort: date | None = None) -> Outcome:
        return window_outcome(record, variant, found, window, successors, cohort)

    return Evaluation(
        variant=variant,
        crisis=outcome(CRISIS_WINDOW, REFERENCE_WINDOW[0]),
        reference=outcome(REFERENCE_WINDOW),
        placebo_after=outcome(PLACEBO_AFTER_WINDOW, PLACEBO_BEFORE_WINDOW[0]),
        placebo_before=outcome(PLACEBO_BEFORE_WINDOW),
        rolling=tuple(outcome(window) for window in rolling_windows()),
    )


@dataclass(frozen=True)
class Summary:
    """The tests of one evaluation, over the custodians kept."""

    crisis: Tally
    reference: Tally
    placebo_after: Tally
    placebo_before: Tally
    p: float
    placebo_p: float
    rolling_windows: int
    above_rolling: bool

    @property
    def crisis_above_reference(self) -> bool:
        return self.crisis.hazard > self.reference.hazard


def summarise(evaluation: Evaluation, keep: Bools, config: Config) -> Summary:
    crisis, reference = tally(evaluation.crisis, keep), tally(evaluation.reference, keep)
    after, before = tally(evaluation.placebo_after, keep), tally(evaluation.placebo_before, keep)
    rolling = [tally(outcome, keep) for outcome in evaluation.rolling]
    counted = [t.hazard for t in rolling if t.at_risk >= config.departure_rolling_min_at_risk]
    above = bool(counted) and crisis.at_risk > 0 and crisis.hazard > max(counted)
    return Summary(
        crisis=crisis,
        reference=reference,
        placebo_after=after,
        placebo_before=before,
        p=one_sided_p(crisis, reference),
        placebo_p=one_sided_p(after, before),
        rolling_windows=len(counted),
        above_rolling=above,
    )


def leave_one_out_stable(evaluation: Evaluation, config: Config) -> bool:
    """Whether the primary test (p below alpha) and the rolling comparison both hold with each
    custodian removed in turn. Removing a custodian never at risk changes nothing."""
    outcomes = (evaluation.crisis, evaluation.reference, *evaluation.rolling)
    ever = np.logical_or.reduce([outcome.at_risk for outcome in outcomes])
    everyone = np.ones_like(ever)
    for row in np.flatnonzero(ever):
        keep = everyone.copy()
        keep[row] = False
        summary = summarise(evaluation, keep, config)
        if not (summary.p < config.alpha and summary.above_rolling):
            return False
    return True


def p_band(p: float, config: Config) -> str:
    if np.isnan(p):
        return NOT_COMPUTABLE
    if p < config.alpha / HYPOTHESES_STATED:
        return FAMILY_BOUND
    return BELOW_ALPHA if p < config.alpha else ALPHA_OR_ABOVE


def decide(
    primary: Summary, others: Sequence[tuple[Variant, Summary]], loo_stable: bool, config: Config
) -> str:
    """The decision rule fixed in docs/hypotheses-exploratory.md (O1)."""
    necessary = (
        primary.crisis.departures >= config.k_min
        and primary.p < config.alpha
        and primary.above_rolling
        and primary.placebo_p >= config.alpha
    )
    if not necessary:
        return NOT_ESTABLISHED
    ruled = [summary for variant, summary in others if variant.in_rule]
    directions = all(s.crisis_above_reference for s in ruled)
    significant = all(s.p < config.alpha for s in ruled)
    if primary.p < config.alpha / HYPOTHESES_STATED and loo_stable and directions and significant:
        return HIGH
    if loo_stable and directions:
        return MODERATE
    return LOW


# ---- successor-like pseudonyms ---------------------------------------------------------------
def successor_matrix(
    record: Record,
    events: pl.DataFrame,
    entities_p: pl.DataFrame,
    candidates: Bools,
    config: Config,
) -> Bools:
    """For each candidate (custodian, live silence start): is there an internal person who sent
    nothing in the quiet weeks before it, sent in the silence, and wrote there to at least
    `successor_overlap` of the custodian's recent recipients (and at least
    `successor_min_shared` of them)? Such a pseudonym may be the same person under an address
    identity resolution did not merge, or a successor in the role."""
    persons = entities_p.filter((pl.col("type") == vocab.PERSON) & pl.col("is_internal"))
    internal = persons.get_column("pid").implode()
    day = pl.col("ts_hour").dt.date()
    dated = events.filter(day.is_between(config.plausible_start, config.plausible_end))
    dated = dated.filter(pl.col("sender_pid").is_in(internal)).with_columns(
        _week_column(record.first_week)
    )
    sender_weeks = dated.select("sender_pid", "column").unique()
    pairs = (
        dated.filter(
            pl.col("recipient_pid").is_in(internal)
            & (pl.col("recipient_pid") != pl.col("sender_pid"))
        )
        .select("sender_pid", "recipient_pid", "column")
        .unique()
    )
    result = np.zeros_like(candidates)
    silence = config.departure_silence_weeks
    for row, column in zip(*np.nonzero(candidates), strict=True):
        pid = record.custodians[row]
        result[row, column] = _has_successor(pid, int(column), pairs, sender_weeks, silence, config)
    return result


def _has_successor(
    pid: str,
    column: int,
    pairs: pl.DataFrame,
    sender_weeks: pl.DataFrame,
    silence: int,
    config: Config,
) -> bool:
    before = pl.col("column").is_between(column - config.departure_lookback_weeks, column - 1)
    during = pl.col("column").is_between(column, column + silence - 1)
    contacts = (
        pairs.filter((pl.col("sender_pid") == pid) & before).get_column("recipient_pid").unique()
    )
    if contacts.is_empty():
        return False
    needed = max(
        config.successor_min_shared, int(np.ceil(config.successor_overlap * len(contacts)))
    )
    shared = (
        pairs.filter(during & pl.col("recipient_pid").is_in(contacts.implode()))
        .filter(pl.col("sender_pid") != pid)
        .group_by("sender_pid")
        .agg(pl.col("recipient_pid").n_unique().alias("shared"))
        .filter(pl.col("shared") >= needed)
    )
    if shared.is_empty():
        return False
    quiet = pl.col("column").is_between(column - config.successor_quiet_weeks, column - 1)
    recent = sender_weeks.filter(quiet).get_column("sender_pid").unique().implode()
    return not shared.filter(~pl.col("sender_pid").is_in(recent)).is_empty()


def successor_candidates(record: Record, variant: Variant) -> Bools:
    """Live silence starts of the primary definition inside any evaluated window."""
    found = silences(record, variant)
    windows = (
        CRISIS_WINDOW,
        REFERENCE_WINDOW,
        PLACEBO_AFTER_WINDOW,
        PLACEBO_BEFORE_WINDOW,
        *rolling_windows(),
    )
    inside = np.zeros(record.weeks, dtype=np.bool_)
    for window in windows:
        first, last = record.columns(window)
        inside[first : last + 1] = True
    return found.live & inside[np.newaxis, :]


# ---- tables ----------------------------------------------------------------------------------
@dataclass(frozen=True)
class Result:
    periods: pl.DataFrame
    tests: pl.DataFrame


SuccessorFinder = Callable[[Record, Bools], Bools]


def run(record: Record, find_successors: SuccessorFinder, config: Config) -> Result:
    every = variants(config)
    primary = every[0]
    successors = find_successors(record, successor_candidates(record, primary))
    evaluations = [evaluate(record, variant, successors) for variant in every]
    keep = np.ones(len(record.custodians), dtype=np.bool_)
    summaries = [summarise(evaluation, keep, config) for evaluation in evaluations]
    loo_stable = leave_one_out_stable(evaluations[0], config)
    outcome = decide(
        summaries[0], list(zip(every[1:], summaries[1:], strict=True)), loo_stable, config
    )
    return Result(
        periods=_periods(record, evaluations[0], summaries[0]),
        tests=_tests(every, summaries, loo_stable, outcome, config),
    )


def _periods(record: Record, evaluation: Evaluation, summary: Summary) -> pl.DataFrame:
    # A week belongs to the part holding its Monday, as a week belongs to a window.
    last_before = record.columns((CRISIS_WINDOW[0], CRISIS_SPLIT - timedelta(days=1)))[1]
    weeks = evaluation.crisis.departure_week
    early = int(((weeks != NO_WEEK) & (weeks <= last_before)).sum())
    crisis = summary.crisis
    rows = [
        (CRISIS, CRISIS_WINDOW, crisis),
        (REFERENCE, REFERENCE_WINDOW, summary.reference),
        (PLACEBO_AFTER, PLACEBO_AFTER_WINDOW, summary.placebo_after),
        (PLACEBO_BEFORE, PLACEBO_BEFORE_WINDOW, summary.placebo_before),
    ]
    split_rows = [
        (SPLIT_BEFORE, (CRISIS_WINDOW[0], CRISIS_SPLIT - timedelta(days=1)), early),
        (SPLIT_FROM, (CRISIS_SPLIT, CRISIS_WINDOW[1]), crisis.departures - early),
    ]
    records: list[dict[str, object]] = [
        {
            "period": period,
            "period_start": window[0],
            "period_end": window[1],
            "at_risk": t.at_risk,
            "departures": t.departures,
            "record_ends": t.record_ends,
            "hazard": t.hazard if t.at_risk else None,
        }
        for period, window, t in rows
    ]
    records += [
        {
            "period": period,
            "period_start": window[0],
            "period_end": window[1],
            "at_risk": crisis.at_risk,
            "departures": departures,
            "record_ends": None,
            "hazard": departures / crisis.at_risk if crisis.at_risk else None,
        }
        for period, window, departures in split_rows
    ]
    for order, row in enumerate(records, start=1):
        row["order"] = order
    return pl.DataFrame(records, schema=schemas.table("departure_results").polars_schema)


def _tests(
    every: Sequence[Variant],
    summaries: Sequence[Summary],
    loo_stable: bool,
    outcome: str,
    config: Config,
) -> pl.DataFrame:
    rows = []
    for order, (variant, s) in enumerate(zip(every, summaries, strict=True), start=1):
        is_primary = variant.name == PRIMARY
        tallies = (s.crisis, s.reference, s.placebo_after, s.placebo_before)
        rows.append(
            {
                "order": order,
                "variant": variant.name,
                "in_rule": variant.in_rule,
                "crisis_above_reference": s.crisis_above_reference,
                "p": None if np.isnan(s.p) else s.p,
                "p_band": p_band(s.p, config),
                "placebo_p": None if np.isnan(s.placebo_p) else s.placebo_p,
                "placebo_p_band": p_band(s.placebo_p, config),
                "rolling_windows": s.rolling_windows,
                "above_rolling": s.above_rolling,
                "loo_stable": loo_stable if is_primary else None,
                "outcome": outcome if is_primary else None,
                "smallest_at_risk": min(t.at_risk for t in tallies),
                "smallest_cell": smallest_cell(s.crisis, s.reference),
                "placebo_smallest_cell": smallest_cell(s.placebo_after, s.placebo_before),
            }
        )
    return pl.DataFrame(rows, schema=schemas.table("departure_test_results").polars_schema)


def departure_tables(events: pl.DataFrame, entities_p: pl.DataFrame, config: Config) -> Result:
    """H26 on the restricted events: the period counts and the tests."""
    record = build_record(events, entities_p, config)

    def find(record: Record, candidates: Bools) -> Bools:
        return successor_matrix(record, events, entities_p, candidates, config)

    return run(record, find, config)
