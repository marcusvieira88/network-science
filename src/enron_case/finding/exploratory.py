"""Hypotheses H5–H25 (recorded as E1–E21 in docs/hypotheses-exploratory.md; H25 post hoc).

Every hypothesis is a paired, within-custodian difference of a ratio between fixed windows, so
neither a change in which mailboxes hold mail nor a change in how much mail was kept can
produce it. Windows are fixed by public dates, not searched for in the data.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import numpy as np
import polars as pl
from scipy.stats import wilcoxon

from enron_case.config import (
    CRISIS_WINDOW,
    PLACEBO_AFTER_WINDOW,
    PLACEBO_BEFORE_WINDOW,
    REFERENCE_WINDOW,
    Config,
)
from enron_case.contracts import schemas, vocab
from enron_case.finding import stats

UP, DOWN = 1, -1
PLACEBO_FRACTION = 0.5
WORK_START, WORK_END = 7, 19
BROADCAST_SENT = 5
LAST_WEEKDAY = 5  # Friday: weekday numbers run 1 = Monday ... 7 = Sunday
BROADCAST_RECEIVED = 20
TOP_RECIPIENTS = 3
TOP_SENDERS = 3
# Houston is UTC-6, and UTC-5 between the US daylight-saving switches (2 a.m. local: 08:00 UTC
# in spring, 07:00 UTC in autumn).
DST_UTC: tuple[tuple[datetime, datetime], ...] = tuple(
    (datetime(y, m1, d1, 8, tzinfo=UTC), datetime(y, m2, d2, 7, tzinfo=UTC))
    for y, m1, d1, m2, d2 in (
        (1998, 4, 5, 10, 25),
        (1999, 4, 4, 10, 31),
        (2000, 4, 2, 10, 29),
        (2001, 4, 1, 10, 28),
        (2002, 4, 7, 10, 27),
    )
)
CAVEATS = schemas.EXPLORATORY_CAVEATS
# Measures that read rows outside their window; volume equalisation (which keeps only in-window
# rows) cannot be applied to them.
LOOKBACK_MEASURES = frozenset({"H19"})

Window = tuple[date, date]

_, CC, BCC = vocab.RECIPIENT_ROLES
CONFIDENT, INCONCLUSIVE, NOT_SUPPORTED = schemas.EXPLORATORY_OUTCOMES
FIRST_FAMILY, SECOND_FAMILY, POST_HOC_FAMILY = schemas.EXPLORATORY_FAMILIES

WindowMeasure = Callable[[pl.DataFrame], pl.DataFrame]  # rows of one window -> pid, value, n
# A measure sees the full message tables and the window, because some measures (E12, E15) need
# rows outside the window: the reverse direction, or the weeks before it.
Measure = Callable[["Tables", Window], pl.DataFrame]
LOOKBACK_DAYS = 182  # E15: 26 weeks before each window


@dataclass(frozen=True)
class Exploratory:
    id: str
    direction: int
    description: str


FAMILY: tuple[Exploratory, ...] = (
    Exploratory("H5", UP, "after-hours share of sent messages (weekdays)"),
    Exploratory("H6", UP, "weekend share of sent messages"),
    Exploratory("H7", UP, "share of sent messages with a Bcc recipient"),
    Exploratory("H8", UP, "share of sent messages with a Cc recipient"),
    Exploratory("H9", UP, "mean recipients per sent message"),
    Exploratory("H10", UP, "share of sent messages with five or more recipients"),
    Exploratory("H11", DOWN, "distinct internal contacts per active week"),
    Exploratory("H12", UP, "sent messages per active week"),
    Exploratory("H13", UP, "share of sent messages to the top three recipients"),
    Exploratory("H14", UP, "share of received messages sent to 20 or more"),
    Exploratory("H15", UP, "share of sent messages with one recipient (derived from H14)"),
    Exploratory("H16", UP, "share of sent-to contacts who also wrote to the custodian"),
    Exploratory("H17", UP, "share of sent messages to another custodian"),
    Exploratory("H18", UP, "share of received messages from another custodian"),
    Exploratory("H19", DOWN, "share of contacts new against the prior 26 weeks"),
    Exploratory("H20", UP, "distinct senders per active week"),
    Exploratory("H21", UP, "share of received messages from the top three senders"),
    Exploratory("H22", DOWN, "share of received messages from external senders"),
    Exploratory("H23", UP, "share of weeks with at least one sent message"),
    Exploratory("H24", DOWN, "share of sent messages to a list, role or system address"),
    Exploratory("H25", UP, "share of the other custodians exchanged mail with (post hoc)"),
)


# ---- message tables --------------------------------------------------------------------------
def _with_local_time(df: pl.DataFrame) -> pl.DataFrame:
    ts = pl.col("ts_hour")
    summer = pl.any_horizontal([(ts >= start) & (ts < end) for start, end in DST_UTC])
    local = ts + pl.duration(hours=pl.when(summer).then(-5).otherwise(-6))
    return df.with_columns(
        local.dt.date().alias("day"),
        local.dt.hour().alias("hour"),
        local.dt.weekday().alias("weekday"),  # 1 = Monday … 7 = Sunday
        local.dt.date().dt.truncate("1w").alias("week"),
    )


def sent_messages(events: pl.DataFrame, custodians: pl.Series) -> pl.DataFrame:
    """One row per message sent by a custodian, with every recipient (not only the network)."""
    sent = events.filter(pl.col("sender_pid").is_in(custodians.implode()))
    internal_person = (pl.col("recipient_type") == vocab.PERSON) & pl.col("recipient_internal")
    messages = sent.group_by("msg_pid").agg(
        pl.col("sender_pid").first().alias("pid"),
        pl.col("ts_hour").first(),
        pl.col("n_recipients").first(),
        (pl.col("role") == BCC).any().alias("has_bcc"),
        (pl.col("role") == CC).any().alias("has_cc"),
        pl.col("recipient_pid").sort().alias("recipients"),
        pl.col("recipient_pid").filter(internal_person).sort().alias("internal_recipients"),
        pl.col("recipient_pid")
        .filter(pl.col("recipient_type") == vocab.PERSON)
        .sort()
        .alias("person_recipients"),
        (pl.col("recipient_type") != vocab.PERSON).any().alias("has_nonperson"),
        (
            pl.col("recipient_pid").is_in(custodians.implode())
            & (pl.col("recipient_pid") != pl.col("sender_pid"))
        )
        .any()
        .alias("to_custodian"),
    )
    return _with_local_time(messages.sort("msg_pid"))


def received_messages(events: pl.DataFrame, custodians: pl.Series) -> pl.DataFrame:
    received = events.filter(pl.col("recipient_pid").is_in(custodians.implode()))
    rows = received.select(
        pl.col("recipient_pid").alias("pid"),
        "msg_pid",
        "ts_hour",
        "n_recipients",
        "sender_pid",
        "sender_internal",
        (
            pl.col("sender_pid").is_in(custodians.implode())
            & (pl.col("sender_pid") != pl.col("recipient_pid"))
        ).alias("from_custodian"),
    ).unique(subset=["pid", "msg_pid"], keep="first")
    return _with_local_time(rows.sort("pid", "msg_pid"))


# ---- measures --------------------------------------------------------------------------------
def _share(condition: pl.Expr) -> WindowMeasure:
    def measure(df: pl.DataFrame) -> pl.DataFrame:
        return df.group_by("pid").agg(
            condition.cast(pl.Float64).mean().alias("value"), pl.len().alias("n")
        )

    return measure


def _mean_recipients(df: pl.DataFrame) -> pl.DataFrame:
    return df.group_by("pid").agg(
        pl.col("n_recipients").cast(pl.Float64).mean().alias("value"), pl.len().alias("n")
    )


def _contacts_per_week(df: pl.DataFrame) -> pl.DataFrame:
    weekly = (
        df.explode("internal_recipients")
        .group_by("pid", "week")
        .agg(pl.col("internal_recipients").drop_nulls().n_unique().alias("contacts"))
    )
    counts = df.group_by("pid").agg(pl.len().alias("n"))
    return (
        weekly.group_by("pid")
        .agg(pl.col("contacts").cast(pl.Float64).mean().alias("value"))
        .join(counts, on="pid")
    )


def _messages_per_week(df: pl.DataFrame) -> pl.DataFrame:
    return df.group_by("pid").agg(
        (pl.len() / pl.col("week").n_unique()).cast(pl.Float64).alias("value"),
        pl.len().alias("n"),
    )


def _top_recipient_share(df: pl.DataFrame) -> pl.DataFrame:
    per_recipient = (
        df.explode("recipients")
        .group_by("pid", "recipients")
        .len()
        .sort(["pid", "len", "recipients"], descending=[False, True, False])
    )
    top = per_recipient.group_by("pid", maintain_order=True).head(TOP_RECIPIENTS)
    tops = top.group_by("pid").agg(pl.col("recipients").alias("top"))
    joined = df.join(tops, on="pid")
    hit = pl.col("recipients").list.set_intersection(pl.col("top")).list.len() > 0
    return joined.group_by("pid").agg(
        hit.cast(pl.Float64).mean().alias("value"), pl.len().alias("n")
    )


@dataclass(frozen=True)
class Tables:
    sent: pl.DataFrame
    received: pl.DataFrame
    # Custodian pseudonyms; the retention check keeps only contacts who are custodians.
    custodians: frozenset[str] = frozenset()


def _in(df: pl.DataFrame, window: Window) -> pl.DataFrame:
    return df.filter((pl.col("day") >= window[0]) & (pl.col("day") <= window[1]))


def _windowed(side: str, measure: WindowMeasure) -> Measure:
    def run(tables: Tables, window: Window) -> pl.DataFrame:
        return measure(_in(getattr(tables, side), window))

    return run


def _top_sender_share(df: pl.DataFrame) -> pl.DataFrame:
    per_sender = (
        df.group_by("pid", "sender_pid")
        .len()
        .sort(["pid", "len", "sender_pid"], descending=[False, True, False])
    )
    top = per_sender.group_by("pid", maintain_order=True).head(TOP_SENDERS)
    joined = df.join(
        top.select("pid", "sender_pid", pl.lit(True).alias("top")),
        on=["pid", "sender_pid"],
        how="left",
    )
    return joined.group_by("pid").agg(
        pl.col("top").fill_null(False).cast(pl.Float64).mean().alias("value"),
        pl.len().alias("n"),
    )


def _senders_per_week(df: pl.DataFrame) -> pl.DataFrame:
    weekly = df.group_by("pid", "week").agg(pl.col("sender_pid").n_unique().alias("senders"))
    counts = df.group_by("pid").agg(pl.len().alias("n"))
    return (
        weekly.group_by("pid")
        .agg(pl.col("senders").cast(pl.Float64).mean().alias("value"))
        .join(counts, on="pid")
    )


def _sent_contacts(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.explode("person_recipients")
        .drop_nulls("person_recipients")
        .select("pid", pl.col("person_recipients").alias("contact"))
        .unique()
    )


def _reciprocity(tables: Tables, window: Window) -> pl.DataFrame:
    """Share of the custodian's sent-to contacts who sent the custodian anything in the same
    window. Not a reply: headers carry no thread, so any message in the window counts."""
    sent = _in(tables.sent, window)
    contacts = _sent_contacts(sent)
    wrote_to_custodian = (
        _in(tables.received, window)
        .select("pid", pl.col("sender_pid").alias("contact"))
        .unique()
        .with_columns(pl.lit(True).alias("back"))
    )
    joined = contacts.join(wrote_to_custodian, on=["pid", "contact"], how="left")
    shares = joined.group_by("pid").agg(
        pl.col("back").fill_null(False).cast(pl.Float64).mean().alias("value")
    )
    return shares.join(sent.group_by("pid").agg(pl.len().alias("n")), on="pid")


def _reciprocity_between_custodians(tables: Tables, window: Window) -> pl.DataFrame:
    """Reciprocity counting only contacts who are themselves custodians. Their mail is collected
    from both sides (a message from one survives in their own sent folder even if the other
    custodian's inbox lost it), so how much inbox mail was kept cannot move this measure. `n` is the
    smaller of the custodian's sent and received counts, so both must meet the minimum."""
    sent = _in(tables.sent, window)
    received = _in(tables.received, window)
    custodians = list(tables.custodians)
    contacts = _sent_contacts(sent).filter(pl.col("contact").is_in(custodians))
    wrote_to_custodian = (
        received.select("pid", pl.col("sender_pid").alias("contact"))
        .unique()
        .with_columns(pl.lit(True).alias("back"))
    )
    shares = (
        contacts.join(wrote_to_custodian, on=["pid", "contact"], how="left")
        .group_by("pid")
        .agg(pl.col("back").fill_null(False).cast(pl.Float64).mean().alias("value"))
    )
    counts = (
        sent.group_by("pid")
        .len()
        .join(received.group_by("pid").len(), on="pid", suffix="_received")
    )
    n = counts.select("pid", pl.min_horizontal("len", "len_received").alias("n"))
    return shares.join(n, on="pid")


# A share of "the other custodians" needs at least one other custodian.
MIN_CUSTODIANS_FOR_SHARE = 2


def _core_density(tables: Tables, window: Window, *, received: bool) -> pl.DataFrame:
    """Share of the other custodians each custodian is in contact with in the window: written
    to, and with `received` also heard from (any surviving copy counts). `n` is the smaller of
    the custodian's sent and received counts, so both must meet the minimum."""
    custodians = sorted(tables.custodians)
    if len(custodians) < MIN_CUSTODIANS_FOR_SHARE:
        return pl.DataFrame(schema={"pid": pl.String, "value": pl.Float64, "n": pl.UInt32})
    sent, inbox = _in(tables.sent, window), _in(tables.received, window)
    frames = [_sent_contacts(sent)]
    if received:
        frames.append(inbox.select("pid", pl.col("sender_pid").alias("contact")))
    contacts = (
        pl.concat(frames)
        .filter(pl.col("contact").is_in(custodians) & (pl.col("contact") != pl.col("pid")))
        .unique()
        .group_by("pid")
        .agg(pl.len().alias("contacts"))
    )
    counts = (
        sent.group_by("pid")
        .len()
        .join(inbox.group_by("pid").len(), on="pid", how="full", coalesce=True, suffix="_in")
        .fill_null(0)
    )
    return counts.join(contacts, on="pid", how="left").select(
        "pid",
        (pl.col("contacts").fill_null(0) / (len(custodians) - 1)).cast(pl.Float64).alias("value"),
        pl.min_horizontal("len", "len_in").alias("n"),
    )


def _core_ego_density(tables: Tables, window: Window) -> pl.DataFrame:
    """H25: contact in either direction (the per-custodian form of core density)."""
    return _core_density(tables, window, received=True)


def _core_out_density(tables: Tables, window: Window) -> pl.DataFrame:
    """H25's retention measure: only the custodians written to, which no inbox can move."""
    return _core_density(tables, window, received=False)


@dataclass(frozen=True)
class RetentionRule:
    """A measure that inbox retention cannot move, and the caveat recorded when it fails."""

    measure: Measure
    caveat: str


# Artifact checks for H5–H25, added after the data-science review (H16) and with H25. A
# hypothesis that fails its check cannot be held true.
RETENTION_CHECKS: dict[str, RetentionRule] = {
    "H16": RetentionRule(_reciprocity_between_custodians, schemas.RETENTION_FAILED["H16"]),
    "H25": RetentionRule(_core_out_density, schemas.RETENTION_FAILED["H25"]),
}


def _new_contact_share(tables: Tables, window: Window) -> pl.DataFrame:
    sent = _in(tables.sent, window)
    start = window[0] - timedelta(days=LOOKBACK_DAYS)
    prior = _sent_contacts(_in(tables.sent, (start, window[0] - timedelta(days=1))))
    active_before = prior.select("pid").unique()
    current = _sent_contacts(sent).join(active_before, on="pid")  # needs a history to compare
    known = prior.with_columns(pl.lit(True).alias("known"))
    joined = current.join(known, on=["pid", "contact"], how="left")
    shares = joined.group_by("pid").agg(
        pl.col("known").is_null().cast(pl.Float64).mean().alias("value")
    )
    return shares.join(sent.group_by("pid").agg(pl.len().alias("n")), on="pid")


def _active_week_share(tables: Tables, window: Window) -> pl.DataFrame:
    """Share of the window's full Monday-to-Sunday weeks with a sent message (partial weeks at
    the window edges are left out of both numerator and denominator)."""
    first = window[0] + timedelta(days=(7 - window[0].weekday()) % 7)
    last = window[1] - timedelta(days=(window[1].weekday() + 1) % 7)
    weeks = ((last - first).days + 1) // 7
    sent = _in(tables.sent, window)
    full = sent.filter((pl.col("day") >= first) & (pl.col("day") <= last))
    counts = sent.group_by("pid").agg(pl.len().alias("n"))
    return (
        full.group_by("pid")
        .agg((pl.col("week").n_unique() / weeks).cast(pl.Float64).alias("value"))
        .join(counts, on="pid", how="right")
        .with_columns(pl.col("value").fill_null(0.0))
        .select("pid", "value", "n")
    )


def _weekday_share(condition: pl.Expr) -> WindowMeasure:
    """Share among weekday messages only, so weekend volume cannot move it."""
    share = _share(condition)

    def measure(df: pl.DataFrame) -> pl.DataFrame:
        return share(df.filter(pl.col("weekday") <= LAST_WEEKDAY))

    return measure


after_hours = (pl.col("weekday") <= LAST_WEEKDAY) & (
    (pl.col("hour") < WORK_START) | (pl.col("hour") >= WORK_END)
)
MEASURES: dict[str, Measure] = {
    "H5": _windowed("sent", _weekday_share(after_hours)),
    "H6": _windowed("sent", _share(pl.col("weekday") > LAST_WEEKDAY)),
    "H7": _windowed("sent", _share(pl.col("has_bcc"))),
    "H8": _windowed("sent", _share(pl.col("has_cc"))),
    "H9": _windowed("sent", _mean_recipients),
    "H10": _windowed("sent", _share(pl.col("n_recipients") >= BROADCAST_SENT)),
    "H11": _windowed("sent", _contacts_per_week),
    "H12": _windowed("sent", _messages_per_week),
    "H13": _windowed("sent", _top_recipient_share),
    "H14": _windowed("received", _share(pl.col("n_recipients") >= BROADCAST_RECEIVED)),
    "H15": _windowed("sent", _share(pl.col("n_recipients") == 1)),
    "H16": _reciprocity,
    "H17": _windowed("sent", _share(pl.col("to_custodian"))),
    "H18": _windowed("received", _share(pl.col("from_custodian"))),
    "H19": _new_contact_share,
    "H20": _windowed("received", _senders_per_week),
    "H21": _windowed("received", _top_sender_share),
    "H22": _windowed("received", _share(~pl.col("sender_internal"))),
    "H23": _active_week_share,
    "H24": _windowed("sent", _share(pl.col("has_nonperson"))),
    "H25": _core_ego_density,
}


# ---- paired comparison ---------------------------------------------------------------------
def paired_differences(
    tables: Tables, measure: Measure, after: Window, before: Window, min_messages: int
) -> np.ndarray:
    """Per custodian with at least `min_messages` in both windows: measure(after) −
    measure(before), ordered by pseudonym so the seeded bootstrap is reproducible."""
    a = measure(tables, after).filter(pl.col("n") >= min_messages)
    b = measure(tables, before).filter(pl.col("n") >= min_messages)
    paired = a.join(b, on="pid", suffix="_before").sort("pid")
    diff = paired.get_column("value") - paired.get_column("value_before")
    out: np.ndarray = diff.to_numpy().astype(float)
    return out


@dataclass(frozen=True)
class Comparison:
    n: int
    median: float
    ci_low: float
    ci_high: float
    p: float


def compare(d: np.ndarray, config: Config, stream: int) -> Comparison:
    if len(d) < 2:
        return Comparison(len(d), float("nan"), float("nan"), float("nan"), 1.0)
    if np.all(d == 0):
        return Comparison(len(d), 0.0, 0.0, 0.0, 1.0)  # no change at all: a flat result
    rng = stats.rng_for(config.seed, 100 + stream)
    low, high = stats.median_bootstrap_ci(d, config.exploratory_bootstrap_reps, rng)
    p = float(wilcoxon(d, alternative="two-sided").pvalue)
    return Comparison(len(d), float(np.median(d)), low, high, p)


def _placebo_passes(direction: int, crisis: Comparison, placebo: Comparison) -> bool:
    if placebo.n < 2 or np.isnan(placebo.median):
        return False
    if placebo.ci_low <= 0 <= placebo.ci_high:
        return True
    return direction * placebo.median < PLACEBO_FRACTION * direction * crisis.median


def _loo_stable(direction: int, d: np.ndarray) -> bool:
    if len(d) < 3:
        return False
    return all(direction * float(np.median(np.delete(d, i))) > 0 for i in range(len(d)))


SECOND_FAMILY_FROM = 11  # H15 (11th) onwards was stated after H5–H14 were computed
POST_HOC_FROM = 21  # H25 (21st) was stated after every other result and after prior work
FIRST_ID = 5  # H1–H4 are the pre-registered hypotheses; this family continues the numbering


def family_of(order: int) -> str:
    """When the hypothesis at 0-based position `order` was stated."""
    if order + 1 >= POST_HOC_FROM:
        return POST_HOC_FAMILY
    return FIRST_FAMILY if order + 1 < SECOND_FAMILY_FROM else SECOND_FAMILY


EQUALISED_STREAM = 200


def _subsample(df: pl.DataFrame, caps: pl.DataFrame, cap: str, seed: int) -> pl.DataFrame:
    """At most `cap` rows per custodian, chosen with a seeded shuffle. Rows are sorted after the
    join (which keeps no order) so the same seed picks the same messages on every run."""
    return (
        df.join(caps.select("pid", pl.col(cap).alias("_cap")), on="pid")
        .sort("pid", "msg_pid")
        .with_columns(pl.int_range(pl.len()).shuffle(seed=seed).over("pid").alias("_k"))
        .filter(pl.col("_k") < pl.col("_cap"))
        .drop("_cap", "_k")
    )


def volume_equalised(
    tables: Tables, measure: Measure, after: Window, before: Window, config: Config, stream: int
) -> Comparison:
    """The paired comparison with mail volume held equal: each custodian's sent and received
    messages in both windows are subsampled to the smaller of the two windows' counts, the
    measure is recomputed, and each custodian's difference is averaged over the subsamples."""
    sent_a, sent_b = _in(tables.sent, after), _in(tables.sent, before)
    recv_a, recv_b = _in(tables.received, after), _in(tables.received, before)

    def caps(a: pl.DataFrame, b: pl.DataFrame, name: str) -> pl.DataFrame:
        counts = a.group_by("pid").len().join(b.group_by("pid").len(), on="pid", suffix="_b")
        return counts.select("pid", pl.min_horizontal("len", "len_b").alias(name))

    limits = (
        caps(sent_a, sent_b, "sent_cap")
        .join(caps(recv_a, recv_b, "recv_cap"), on="pid", how="full", coalesce=True)
        .fill_null(0)
    )
    draws = []
    for rep in range(config.exploratory_equalise_reps):
        seed = config.seed + rep
        sampled = Tables(
            pl.concat(
                [
                    _subsample(sent_a, limits, "sent_cap", seed),
                    _subsample(sent_b, limits, "sent_cap", seed),
                ]
            ),
            pl.concat(
                [
                    _subsample(recv_a, limits, "recv_cap", seed),
                    _subsample(recv_b, limits, "recv_cap", seed),
                ]
            ),
            tables.custodians,
        )
        minimum = config.exploratory_min_messages
        a = measure(sampled, after).filter(pl.col("n") >= minimum)
        b = measure(sampled, before).filter(pl.col("n") >= minimum)
        draws.append(
            a.join(b, on="pid", suffix="_b").select(
                "pid", (pl.col("value") - pl.col("value_b")).alias("d")
            )
        )
    # Mean of sorted values: rows of a group arrive in thread order, and float addition is not
    # associative, so an unsorted mean differs between runs in the last digit.
    per_custodian = pl.concat(draws).group_by("pid").agg(pl.col("d").sort().mean()).sort("pid")
    d = per_custodian.get_column("d").to_numpy().astype(float)
    if len(d) < config.k_min:
        # Too few custodians survive equalisation to publish; reported as not computed.
        return Comparison(len(d), float("nan"), float("nan"), float("nan"), 1.0)
    return compare(d, config, stream)


def family_adjusted(p: float) -> float:
    """p times the family size, capped at 1. The equalised test is run only for the hypotheses
    that survived, so it has no Holm rank of its own; the largest multiplier is the safe one."""
    return min(1.0, len(FAMILY) * p)


RETENTION_STREAM = 300


@dataclass(frozen=True)
class RetentionCheck:
    crisis: Comparison
    placebo: Comparison
    passes: bool


def retention_check(
    tables: Tables, direction: int, measure: Measure, config: Config, order: int
) -> RetentionCheck:
    """The hypothesis recomputed on a measure that inbox retention cannot move. Passes only if
    the crisis change is on the hypothesised side over at least k custodians and the same
    subset shows no comparable pre-crisis change."""
    minimum = config.exploratory_min_messages
    d = paired_differences(tables, measure, CRISIS_WINDOW, REFERENCE_WINDOW, minimum)
    crisis = compare(d, config, RETENTION_STREAM + order)
    placebo = compare(
        paired_differences(tables, measure, PLACEBO_AFTER_WINDOW, PLACEBO_BEFORE_WINDOW, minimum),
        config,
        RETENTION_STREAM + 50 + order,
    )
    passes = (
        crisis.n >= config.k_min
        and stats.on_side(direction, crisis.ci_low, crisis.ci_high)
        and _placebo_passes(direction, crisis, placebo)
    )
    return RetentionCheck(crisis, placebo, passes)


def custodian_tables(events: pl.DataFrame, entities_p: pl.DataFrame) -> Tables:
    """Sent and received messages of the custodians who are internal persons."""
    custodians = entities_p.filter(
        pl.col("is_custodian") & (pl.col("type") == vocab.PERSON) & pl.col("is_internal")
    ).get_column("pid")
    return Tables(
        sent_messages(events, custodians),
        received_messages(events, custodians),
        frozenset(custodians.to_list()),
    )


def run_family(events: pl.DataFrame, entities_p: pl.DataFrame, config: Config) -> pl.DataFrame:
    return run_family_on(custodian_tables(events, entities_p), config)


def run_family_on(tables: Tables, config: Config) -> pl.DataFrame:
    """The `exploratory_results` table for H5–H25."""
    rows = []
    for index, hyp in enumerate(FAMILY):
        measure = MEASURES[hyp.id]
        minimum = config.exploratory_min_messages
        d = paired_differences(tables, measure, CRISIS_WINDOW, REFERENCE_WINDOW, minimum)
        crisis = compare(d, config, index)
        placebo = compare(
            paired_differences(
                tables, measure, PLACEBO_AFTER_WINDOW, PLACEBO_BEFORE_WINDOW, minimum
            ),
            config,
            50 + index,
        )
        rows.append((hyp, d, crisis, placebo))
    p_holm = stats.holm([crisis.p for _h, _d, crisis, _pl in rows])
    out = []
    for order, ((hyp, d, crisis, placebo), ph) in enumerate(zip(rows, p_holm, strict=True)):
        on_side = stats.on_side(hyp.direction, crisis.ci_low, crisis.ci_high)
        placebo_ok = _placebo_passes(hyp.direction, crisis, placebo)
        loo_ok = _loo_stable(hyp.direction, d)
        significant = ph < config.alpha
        valid = hyp.id not in CAVEATS
        if significant and on_side and placebo_ok and loo_ok and valid:
            outcome = CONFIDENT
        elif significant and on_side:
            outcome = INCONCLUSIVE
        else:
            outcome = NOT_SUPPORTED
        equalised = (
            volume_equalised(
                tables,
                MEASURES[hyp.id],
                CRISIS_WINDOW,
                REFERENCE_WINDOW,
                config,
                EQUALISED_STREAM + order,
            )
            if outcome != NOT_SUPPORTED and valid and hyp.id not in LOOKBACK_MEASURES
            else None
        )
        retention = (
            retention_check(tables, hyp.direction, RETENTION_CHECKS[hyp.id].measure, config, order)
            if hyp.id in RETENTION_CHECKS and outcome != NOT_SUPPORTED
            else None
        )
        # The retention comparison has its own custodian count: below k its statistics would
        # describe a group under the minimum, so only its (failed) verdict is kept.
        shown = retention if retention is not None and retention.crisis.n >= config.k_min else None
        caveat = CAVEATS.get(hyp.id, "")
        if retention is not None and not retention.passes:
            outcome = INCONCLUSIVE  # an artifact check failed: cannot be held true
            caveat = RETENTION_CHECKS[hyp.id].caveat
        out.append(
            {
                "order": FIRST_ID + order,
                "hypothesis": hyp.id,
                "family": family_of(order),
                "measure": hyp.description,
                "direction": "up" if hyp.direction == UP else "down",
                "custodians": crisis.n,
                "median_change": crisis.median,
                "ci_low": crisis.ci_low,
                "ci_high": crisis.ci_high,
                "p": crisis.p,
                "p_holm": ph,
                "placebo_custodians": placebo.n,
                "placebo_median": placebo.median,
                "placebo_ci_low": placebo.ci_low,
                "placebo_ci_high": placebo.ci_high,
                "placebo_passes": placebo_ok,
                "loo_stable": loo_ok,
                "outcome": outcome,
                "caveat": caveat,
                "equalised_median": equalised.median if equalised else None,
                "equalised_ci_low": equalised.ci_low if equalised else None,
                "equalised_ci_high": equalised.ci_high if equalised else None,
                "equalised_p": equalised.p if equalised else None,
                "equalised_p_holm": family_adjusted(equalised.p) if equalised else None,
                "retention_median": shown.crisis.median if shown else None,
                "retention_ci_low": shown.crisis.ci_low if shown else None,
                "retention_ci_high": shown.crisis.ci_high if shown else None,
                "retention_passes": retention.passes if retention else None,
            }
        )
    return schemas.conform(
        pl.DataFrame(out, schema=schemas.table("exploratory_results").polars_schema),
        "exploratory_results",
    )
