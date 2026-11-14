"""T071: release variants R0 (restricted, node level), R1 (aggregates) and R2 (R1 + noise)."""

from __future__ import annotations

import dataclasses
from datetime import date

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from enron_case.config import Config
from enron_case.contracts import schemas
from enron_case.errors import PrivacyViolation
from enron_case.release import kanon, mitigate, variants
from enron_case.synth import SynthOutput

K = 5
CONFIG = dataclasses.replace(Config(), k_min=K)
H1_WEEK = date(2000, 1, 3)
H2_WEEK = date(2000, 7, 3)
EDGE_SCHEMA = {
    "week": pl.Date(),
    "src_pid": pl.String(),
    "dst_pid": pl.String(),
    "weight": pl.Float64(),
    "n_messages": pl.Int64(),
}
R1_TABLES = {"weekly_metrics", "degree_distribution", "community_graph", "community_groups"}


def pid(i: int) -> str:
    letters = "abcdefghijklmnopqrstuvwxyz"
    return "p_" + (letters[i // 26] + letters[i % 26]) * 8


def edges(rows: list[tuple[date, int, int]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "week": [r[0] for r in rows],
            "src_pid": [pid(r[1]) for r in rows],
            "dst_pid": [pid(r[2]) for r in rows],
            "weight": [1.0] * len(rows),
            "n_messages": [1] * len(rows),
        },
        schema=EDGE_SCHEMA,
    )


def communities(sizes: dict[int, int]) -> pl.DataFrame:
    rows, i = [], 0
    for community, size in sizes.items():
        for _ in range(size):
            rows.append({"pid": pid(i), "community": community})
            i += 1
    return pl.DataFrame(rows)


def empty_metrics() -> pl.DataFrame:
    return pl.DataFrame(schema=schemas.table("metric_series").polars_schema)


def observed_snapshots(synth: SynthOutput) -> pl.DataFrame:
    return synth.table("snapshots").filter(pl.col("scope") == "observed").drop("scope")


# ---- R0 ---------------------------------------------------------------------------------
def test_r0_is_the_observed_snapshot_edges_without_scope(synth: SynthOutput) -> None:
    snapshots = synth.table("snapshots")
    r0 = variants.build_r0(snapshots)
    assert r0.columns == list(EDGE_SCHEMA)
    observed_rows = snapshots.filter(pl.col("scope") == "observed").height
    assert 0 < observed_rows < snapshots.height
    assert r0.height == observed_rows
    assert_frame_equal(r0, observed_snapshots(synth))


def test_r0_is_node_level_and_cannot_pass_kanon(synth: SynthOutput) -> None:
    r0 = variants.build_r0(synth.table("snapshots"))
    with pytest.raises(PrivacyViolation):
        kanon.assert_no_identifiers(r0)


# ---- R1 ---------------------------------------------------------------------------------
def build_r1_from_fixtures(synth: SynthOutput) -> dict[str, pl.DataFrame]:
    return variants.build_r1(
        observed_snapshots(synth), synth.table("metric_series"), synth.table("communities"), CONFIG
    )


def test_r1_tables_have_no_person_rows(synth: SynthOutput) -> None:
    r1 = build_r1_from_fixtures(synth)
    assert set(r1) == R1_TABLES
    for name, df in r1.items():
        assert schemas.leak_count(df) == 0, name
        assert not {"pid", "src_pid", "dst_pid"} & set(df.columns)


@pytest.mark.parametrize("name", ["weekly_metrics", "community_graph", "community_groups"])
def test_r1_matches_release_fixture(synth: SynthOutput, name: str) -> None:
    r1 = build_r1_from_fixtures(synth)
    assert_frame_equal(schemas.conform(r1[name], name), synth.table(name), check_exact=False)


def test_degree_buckets_per_half_year() -> None:
    hubs, leaves = (0, 1), range(2, 8)
    h1 = [(H1_WEEK, h, leaf) for h in hubs for leaf in leaves]
    h1 += [(H1_WEEK, 2, 0), (H1_WEEK, 3, 3)]  # reverse edge and self loop add no degree
    h2 = [(H2_WEEK, 10 + 2 * i, 11 + 2 * i) for i in range(5)]
    r1 = variants.build_r1(edges(h1 + h2), empty_metrics(), communities({0: 5}), CONFIG)
    got = {
        (p, b): n
        for p, b, n in r1["degree_distribution"].select("period", "degree_bucket", "persons").rows()
    }
    # 2000H1: six leaves of degree 2, two hubs of degree 6. 2000H2: ten persons of degree 1.
    # In 2000H1 the hubs are the only hidden non-zero cell, so the 6 is suppressed as well.
    assert got == {
        ("2000H1", "1"): None,
        ("2000H1", "2-4"): None,
        ("2000H1", "5-9"): None,
        ("2000H1", "10+"): None,
        ("2000H2", "1"): 10,
        ("2000H2", "2-4"): None,
        ("2000H2", "5-9"): None,
        ("2000H2", "10+"): None,
    }


def test_groups_by_size_small_ones_merged_into_other() -> None:
    comm = communities({3: 5, 0: 7, 1: 3, 2: 3, -1: 1})
    r1 = variants.build_r1(edges([]), empty_metrics(), comm, CONFIG)
    groups = dict(r1["community_groups"].rows())
    assert groups == {"G01": 7, "G02": 5, "other": 7}


def test_group_labels_follow_size_not_community_id() -> None:
    comm = communities({5: 6, 2: 9})
    groups = dict(
        variants.build_r1(edges([]), empty_metrics(), comm, CONFIG)["community_groups"].rows()
    )
    assert groups == {"G01": 9, "G02": 6}


def test_ties_with_fewer_than_k_senders_are_dropped() -> None:
    comm = communities({0: 7, 1: 6})  # pids 0-6 in G01, 7-12 in G02
    forward = [(H1_WEEK, s, 7) for s in range(5)]  # five distinct senders G01 -> G02
    back = [(H1_WEEK, s, 0) for s in range(7, 11)]  # four distinct senders G02 -> G01
    graph = variants.build_r1(edges(forward + back), empty_metrics(), comm, CONFIG)[
        "community_graph"
    ]
    assert graph.select("week", "src_group", "dst_group", "weight", "n_messages").rows() == [
        (H1_WEEK, "G01", "G02", 5.0, 5)
    ]


def test_small_other_group_is_not_published_nor_its_ties() -> None:
    comm = communities({0: 6, 1: 3})  # pids 0-5 in G01, 6-8 in other (3 persons)
    rows = [(H1_WEEK, s, 6) for s in range(6)]
    r1 = variants.build_r1(edges(rows), empty_metrics(), comm, CONFIG)
    assert dict(r1["community_groups"].rows()) == {"G01": 6}
    assert r1["community_graph"].height == 0


def test_weekly_metrics_suppressed_below_k() -> None:
    metrics = pl.DataFrame(
        {
            "scope": ["core", "core"],
            "week": [H1_WEEK, H2_WEEK],
            "metric": ["density", "density"],
            "value": [0.2, 0.3],
            "n_active": [4, 5],
            "variant": ["default", "default"],
        }
    )
    out = variants.build_r1(edges([]), metrics, communities({0: 5}), CONFIG)["weekly_metrics"]
    assert out.select("value", "n_active").rows() == [(None, None), (0.3, 5)]


# ---- R2 ---------------------------------------------------------------------------------
def build_r2(synth: SynthOutput, seed: int) -> dict[str, pl.DataFrame]:
    return variants.build_r2(
        observed_snapshots(synth),
        synth.table("metric_series"),
        synth.table("communities"),
        dataclasses.replace(CONFIG, seed=seed),
    )


def test_r2_is_seeded(synth: SynthOutput) -> None:
    first, again, other = build_r2(synth, 1), build_r2(synth, 1), build_r2(synth, 2)
    assert set(first) == R1_TABLES
    for name in first:
        assert first[name].equals(again[name]), name
    assert not first["community_graph"].equals(other["community_graph"])


def test_r2_still_meets_k(synth: SynthOutput) -> None:
    for name, df in build_r2(synth, 3).items():
        kanon.check(name, df, K)


def test_laplace_noise_is_unbiased_on_counts() -> None:
    rng = np.random.default_rng(7)
    true = pl.Series([7] * 20_000, dtype=pl.Int64)
    noisy = mitigate.add_laplace(true, scale=1.0, rng=rng)
    assert noisy.dtype == pl.Int64
    assert not noisy.equals(true)
    mean = noisy.cast(pl.Float64).mean()
    assert isinstance(mean, float)
    assert abs(mean - 7.0) < 0.05


def test_laplace_noise_is_unbiased_on_weights() -> None:
    rng = np.random.default_rng(8)
    true = pl.Series([2.5] * 20_000)
    noisy = mitigate.add_laplace(true, scale=1.0, rng=rng)
    mean = noisy.mean()
    assert isinstance(mean, float)
    assert abs(mean - 2.5) < 0.05


def test_weekly_metrics_publishes_default_variant_only() -> None:
    # A variant next to the default lets default minus variant n_active reveal small groups.
    metrics = pl.DataFrame(
        {
            "scope": ["core"] * 3,
            "week": [H1_WEEK] * 3,
            "metric": ["density"] * 3,
            "value": [0.2, 0.3, 0.4],
            "n_active": [9, 7, 6],
            "variant": ["default", "cap=20", "window=month"],
        }
    )
    out = variants.build_r1(edges([]), metrics, communities({0: 5}), CONFIG)["weekly_metrics"]
    assert out.select("variant", "n_active").rows() == [("default", 9)]


def test_kanon_rejects_a_non_default_variant_in_weekly_metrics() -> None:
    metrics = pl.DataFrame(
        {
            "scope": ["core"],
            "week": [H1_WEEK],
            "metric": ["density"],
            "value": [0.3],
            "n_active": [7],
            "variant": ["cap=20"],
        }
    )
    with pytest.raises(PrivacyViolation):
        kanon.enforce("weekly_metrics", metrics, K)
