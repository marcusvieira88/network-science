"""T033: resolution is a partition, deterministic, order-independent and precise."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from enron_case.contracts import schemas
from enron_case.identity import evaluate, rules, stage
from enron_case.identity.resolve import resolve
from enron_case.synth import SynthOutput
from helpers import ctx_with_fixtures

INPUTS = ("messages", "header_records")


@pytest.fixture
def ran(synth: SynthOutput, tmp_path: Path) -> dict[str, Any]:
    ctx = ctx_with_fixtures("identity", synth, tmp_path, tables=INPUTS)
    stage.run(ctx)
    return {
        "entities": ctx.read("entities"),
        "address_map": ctx.read("address_map"),
        "counts": ctx.read_counts("identity_counts"),
    }


# ---- union-find on hand-built cases ---------------------------------------------------------
def test_canonical_is_smallest_address_and_rule_marks_attachment() -> None:
    occ = {"b.c@org.com": 4, "b.c@ect.org.com": 2, "bc@org.com": 3, "solo@org.com": 1}
    cands = [
        rules.Candidate("b.c@ect.org.com", "b.c@org.com", "N2", 2),
        rules.Candidate("b.c@org.com", "bc@org.com", "N3", 3),
    ]
    amap = resolve(occ, cands).address_map
    assert amap.rows() == [
        ("b.c@ect.org.com", "b.c@ect.org.com", None, 2),
        ("b.c@org.com", "b.c@ect.org.com", "N2", 4),
        ("bc@org.com", "b.c@ect.org.com", "N3", 3),
        ("solo@org.com", "solo@org.com", None, 1),
    ]


def test_blocked_candidates_do_not_merge_and_are_counted_per_cluster_pair() -> None:
    occ = {"a.b@org.com": 1, "a.b@ect.org.com": 1, "a.b@rival.com": 1}
    cands = [
        rules.Candidate("a.b@ect.org.com", "a.b@org.com", "N2", 1),
        rules.Candidate("a.b@org.com", "a.b@rival.com", "N3", 3, rules.GUARD_CROSS_ORG),
        rules.Candidate("a.b@ect.org.com", "a.b@rival.com", "N3", 3, rules.GUARD_CROSS_ORG),
    ]
    result = resolve(occ, cands)
    assert result.address_map.get_column("entity_id").n_unique() == 2
    assert result.blocked_by_guard == {rules.GUARD_CROSS_ORG: 1}


@settings(max_examples=40, deadline=None)
@given(st.randoms(use_true_random=False))
def test_resolution_is_independent_of_input_order(rnd: random.Random) -> None:
    occ = {f"u{i}@org.com": i + 1 for i in range(8)}
    cands = [
        rules.Candidate("u0@org.com", "u3@org.com", "N2", 1),
        rules.Candidate("u3@org.com", "u5@org.com", "N3", 3),
        rules.Candidate("u0@org.com", "u5@org.com", "N3", 3),
        rules.Candidate("u6@org.com", "u7@org.com", "N2", 1),
        rules.Candidate("u1@org.com", "u2@org.com", "N3", 3, rules.GUARD_NAME_ONLY),
    ]
    expected = resolve(occ, cands)
    shuffled = cands[:]
    rnd.shuffle(shuffled)
    items = list(occ.items())
    rnd.shuffle(items)
    again = resolve(dict(items), shuffled)
    assert again.address_map.equals(expected.address_map)
    assert again.blocked_by_guard == expected.blocked_by_guard


# ---- stage on the synthetic corpus ----------------------------------------------------------
def test_every_address_maps_to_exactly_one_entity(ran: dict[str, Any], synth: SynthOutput) -> None:
    amap: pl.DataFrame = ran["address_map"]
    entities: pl.DataFrame = ran["entities"]
    occurrences = rules.address_occurrences(synth.table("messages"))
    assert amap.get_column("addr").is_unique().all()
    assert set(occurrences) <= set(amap.get_column("addr").to_list())
    assert set(amap["entity_id"].to_list()) == set(entities["entity_id"].to_list())
    joined = entities.join(amap.group_by("entity_id").len(), on="entity_id")
    assert (joined["n_addresses"] == joined["len"]).all()
    canonical = amap.filter(pl.col("rule").is_null())
    assert (canonical["addr"] == canonical["entity_id"]).all()
    assert canonical.height == entities.height


def test_outputs_validate_against_contract(ran: dict[str, Any]) -> None:
    schemas.validate(ran["entities"], "entities")
    schemas.validate(ran["address_map"], "address_map")


def test_output_matches_reference_fixture(ran: dict[str, Any], synth: SynthOutput) -> None:
    assert ran["address_map"].equals(synth.table("address_map"))
    assert ran["entities"].equals(synth.table("entities"))


def test_precision_on_ground_truth(ran: dict[str, Any], synth: SynthOutput) -> None:
    entity_of = dict(ran["address_map"].select("addr", "entity_id").iter_rows())
    precision, recall = evaluate.pairwise_scores(entity_of, synth.truth()["address_to_truth"])
    assert precision is not None and precision >= 0.95
    assert recall is not None and recall > 0
    assert ran["counts"]["precision"] == precision
    assert ran["counts"]["recall"] == recall


def test_counts_shape(ran: dict[str, Any]) -> None:
    counts = ran["counts"]
    amap: pl.DataFrame = ran["address_map"]
    assert counts["addresses"] == amap.height
    assert counts["entities"] == ran["entities"].height
    assert sum(counts["merges_by_rule"].values()) == amap.drop_nulls("rule").height
    assert sum(int(k) * v for k, v in counts["cluster_sizes"].items()) == amap.height
    assert sum(counts["entities_by_type"].values()) == ran["entities"].height
    assert counts["manual_checked"] is None and counts["manual_correct"] is None


def test_stage_is_independent_of_input_row_order(synth: SynthOutput, tmp_path: Path) -> None:
    def run(root: Path, shuffle: bool) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, Any]]:
        ctx = ctx_with_fixtures("identity", synth, root, tables=INPUTS)
        if shuffle:
            for name in INPUTS:
                spec = schemas.table(name)
                path = ctx.paths.dir(spec.zone) / spec.filename
                pl.read_parquet(path).sample(fraction=1.0, shuffle=True, seed=3).write_parquet(path)
        stage.run(ctx)
        return ctx.read("address_map"), ctx.read("entities"), ctx.read_counts("identity_counts")

    first = run(tmp_path / "a", shuffle=False)
    second = run(tmp_path / "b", shuffle=True)
    assert first[0].equals(second[0])
    assert first[1].equals(second[1])
    assert first[2] == second[2]


def test_stage_logs_counts_only(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("identity", synth, tmp_path, tables=INPUTS)
    lines: list[str] = []
    ctx.log = lines.append
    stage.run(ctx)
    assert lines
    assert not any("@" in line for line in lines)
    names = [n.lower() for n in synth.truth()["display_names"]]
    assert not any(n in line.lower() for line in lines for n in names)


# ---- evaluation -----------------------------------------------------------------------------
def test_pairwise_scores_on_hand_computed_case() -> None:
    truth = {"a": "T1", "b": "T1", "c": "T1", "d": "T2"}
    predicted = {"a": "a", "b": "a", "c": "c", "d": "a"}
    # predicted pairs ab, ad, bd; true pairs ab, ac, bc; correct ab only
    assert evaluate.pairwise_scores(predicted, truth) == (1 / 3, 1 / 3)
    assert evaluate.pairwise_scores({"a": "a", "d": "d"}, truth) == (None, None)


def test_pairwise_scores_ignore_addresses_without_truth() -> None:
    truth = {"a": "T1", "b": "T1"}
    assert evaluate.pairwise_scores({"a": "a", "b": "a", "z": "a"}, truth) == (1.0, 1.0)


def test_sampler_is_seeded_and_returns_merges_only(ran: dict[str, Any]) -> None:
    amap: pl.DataFrame = ran["address_map"]
    first = evaluate.sample_merges(amap, 5, seed=1)
    assert first.equals(evaluate.sample_merges(amap, 5, seed=1))
    assert first.height == 5 and first["rule"].null_count() == 0
    everything = evaluate.sample_merges(amap, 10_000, seed=1)
    assert everything.height == amap.drop_nulls("rule").height


def test_manual_counts_are_counts() -> None:
    assert evaluate.manual_counts([True, False, True]) == (3, 2)
