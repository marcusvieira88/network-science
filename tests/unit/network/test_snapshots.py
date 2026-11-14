from __future__ import annotations

import polars as pl

from enron_case.config import Config
from enron_case.contracts import schemas
from enron_case.network.snapshots import build_snapshots
from enron_case.synth import SynthOutput
from network_toys import WEEK_1, WEEK_2, Mailbag, Person, entities, people, toy_config

SAMPLE_CONFIG = Config(internal_domain="acme-energy.com")


def test_matches_reference_fixture(synth: SynthOutput) -> None:
    got = build_snapshots(synth.table("events"), synth.table("entities_p"), SAMPLE_CONFIG)
    expected = synth.table("snapshots")
    out = schemas.conform(got, "snapshots")
    schemas.validate(out, "snapshots")
    assert out.equals(expected)


def test_one_snapshot_per_iso_week_and_scope(synth: SynthOutput) -> None:
    snaps = build_snapshots(synth.table("events"), synth.table("entities_p"), SAMPLE_CONFIG)
    weeks = snaps.get_column("week")
    assert (weeks.dt.weekday() == 1).all()  # Monday
    assert set(snaps.get_column("scope").to_list()) == {"core", "observed"}
    assert snaps.select("scope", "week", "src_pid", "dst_pid").is_duplicated().sum() == 0


def test_persons_only_and_in_network_only() -> None:
    a, b = people("a", "b")
    outsider = Person("x", internal=False)
    mailing_list = Person("list", type="list")
    bag = Mailbag()
    bag.send(a, [b, outsider, mailing_list])
    bag.send(a, [b], in_network=False)
    bag.send(mailing_list, [a])
    snaps = build_snapshots(bag.events(), entities([a, b, outsider, mailing_list]), toy_config())
    observed = snaps.filter(pl.col("scope") == "observed")
    assert observed.select("src_pid", "dst_pid").rows() == [(a.pid, b.pid)]
    assert observed.get_column("weight").to_list() == [1 / 3]
    assert observed.get_column("n_messages").to_list() == [1]


def test_weights_sum_to_message_count_for_person_messages() -> None:
    a, b, c, d = people("a", "b", "c", "d")
    bag = Mailbag()
    bag.send(a, [b, c, d])
    bag.send(b, [a])
    bag.send(c, [a, b], week=WEEK_2)
    bag.send(a, [b, c, d], week=WEEK_2)
    snaps = build_snapshots(bag.events(), entities([a, b, c, d]), toy_config())
    observed = snaps.filter(pl.col("scope") == "observed")
    by_week = dict(observed.group_by("week").agg(pl.col("weight").sum()).iter_rows())
    assert by_week[WEEK_1] == 2.0
    assert by_week[WEEK_2] == 2.0


def test_core_keeps_custodian_pairs_only() -> None:
    c1, c2 = people("c1", "c2", custodian=True)
    plain = Person("plain")
    bag = Mailbag()
    bag.send(c1, [c2, plain])
    bag.send(plain, [c1])
    snaps = build_snapshots(bag.events(), entities([c1, c2, plain]), toy_config())
    core = snaps.filter(pl.col("scope") == "core")
    assert core.select("src_pid", "dst_pid").rows() == [(c1.pid, c2.pid)]
    assert snaps.filter(pl.col("scope") == "observed").height == 3


def test_self_ties_and_out_of_window_events_dropped() -> None:
    a, b = people("a", "b")
    bag = Mailbag()
    bag.send(a, [a, b])
    bag.send(a, [b], week=WEEK_1.replace(year=1999))
    snaps = build_snapshots(bag.events(), entities([a, b]), toy_config())
    observed = snaps.filter(pl.col("scope") == "observed")
    assert observed.select("week", "src_pid", "dst_pid").rows() == [(WEEK_1, a.pid, b.pid)]
