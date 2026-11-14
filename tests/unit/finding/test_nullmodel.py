"""Rewiring null: margins preserved per week, structure scrambled, z computed by hand."""

from __future__ import annotations

import math
from datetime import datetime

import polars as pl
import pytest

from enron_case.finding import nullmodel, stats
from enron_case.synth import SynthOutput


def _margin(events: pl.DataFrame, end: str) -> pl.DataFrame:
    week = pl.col("ts_hour").dt.date().dt.truncate("1w").alias("week")
    return (
        events.group_by(week, "in_network", pl.col(end))
        .agg(pl.col("weight").sum())
        .sort("week", "in_network", end)
    )


@pytest.fixture(scope="module")
def events(synth: SynthOutput) -> pl.DataFrame:
    return synth.table("events")


@pytest.fixture(scope="module")
def rewired(events: pl.DataFrame) -> pl.DataFrame:
    return nullmodel.rewire(events, stats.rng_for(11))


@pytest.mark.parametrize("end", ["sender_pid", "recipient_pid"])
def test_rewiring_preserves_weekly_margins(
    events: pl.DataFrame, rewired: pl.DataFrame, end: str
) -> None:
    before, after = _margin(events, end), _margin(rewired, end)
    assert before.select("week", "in_network", end).equals(after.select("week", "in_network", end))
    assert before.get_column("weight").to_list() == pytest.approx(
        after.get_column("weight").to_list()
    )


def test_rewiring_preserves_in_weight_from_each_kind_of_sender(
    events: pl.DataFrame, rewired: pl.DataFrame
) -> None:
    """The network counts only ties from internal persons, so a recipient's in-weight from
    internal persons, external persons and non-persons must each be kept, not only the total."""

    def from_kind(df: pl.DataFrame) -> pl.DataFrame:
        week = pl.col("ts_hour").dt.date().dt.truncate("1w").alias("week")
        keys = [week, "in_network", "sender_type", "sender_internal", "recipient_pid"]
        return (
            df.group_by(keys)
            .agg(pl.col("weight").sum())
            .sort("week", "in_network", "sender_type", "sender_internal", "recipient_pid")
        )

    before, after = from_kind(events), from_kind(rewired)
    keys = ["week", "in_network", "sender_type", "sender_internal", "recipient_pid"]
    assert before.select(keys).equals(after.select(keys))
    assert before.get_column("weight").to_list() == pytest.approx(
        after.get_column("weight").to_list()
    )


def test_rewiring_never_swaps_recipients_across_sender_kinds() -> None:
    """Two events of equal weight in one week, one from a person and one from a list: a
    rewiring that kept only weight and week could hand the person's recipient to the list."""
    base = pl.DataFrame(
        {
            "event_id": ["e1", "e2"],
            "ts_hour": [datetime(2000, 1, 3, 9), datetime(2000, 1, 4, 9)],
            "sender_pid": ["s1", "s2"],
            "sender_type": ["person", "list"],
            "sender_internal": [True, True],
            "weight": [1.0, 1.0],
            "in_network": [True, True],
            "recipient_pid": ["r1", "r2"],
            "recipient_type": ["person", "person"],
            "recipient_internal": [True, True],
            "recipient_org_pid": ["o1", "o1"],
        }
    )
    for seed in range(20):
        out = nullmodel.rewire(base, stats.rng_for(seed))
        assert out.get_column("recipient_pid").to_list() == ["r1", "r2"]


def test_rewiring_moves_recipients_with_their_attributes(
    events: pl.DataFrame, rewired: pl.DataFrame
) -> None:
    assert rewired.columns == events.columns
    assert rewired.height == events.height
    moved = (rewired.get_column("recipient_pid") != events.get_column("recipient_pid")).sum()
    assert moved > events.height // 4
    attrs = ["recipient_pid", "recipient_type", "recipient_internal", "recipient_org_pid"]
    assert (
        rewired.select(attrs).unique().sort(attrs).equals(events.select(attrs).unique().sort(attrs))
    )


def test_rewiring_keeps_sender_side_of_each_event(
    events: pl.DataFrame, rewired: pl.DataFrame
) -> None:
    keep = ["event_id", "msg_pid", "ts_hour", "sender_pid", "weight", "in_network", "role"]
    assert rewired.select(keep).equals(events.select(keep))


def test_rewiring_is_seeded(events: pl.DataFrame, rewired: pl.DataFrame) -> None:
    assert nullmodel.rewire(events, stats.rng_for(11)).equals(rewired)
    assert not nullmodel.rewire(events, stats.rng_for(12)).equals(rewired)


def test_null_z_hand_computed() -> None:
    # null mean 2, sample sd 1
    assert nullmodel.null_z(5.0, [1.0, 2.0, 3.0]) == pytest.approx(3.0)


def test_null_z_when_null_reproduces_the_effect_exactly() -> None:
    assert nullmodel.null_z(2.0, [2.0, 2.0, 2.0]) == 0.0
    assert nullmodel.null_z(3.0, [2.0, 2.0]) == math.inf


def test_null_z_needs_two_replicates() -> None:
    with pytest.raises(stats.InsufficientData):
        nullmodel.null_z(1.0, [0.5])
