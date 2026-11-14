"""T069: the risk stage on the synthetic fixtures, checked against ground truth."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
import pytest

import risk_fakes
from enron_case import config
from enron_case.config import Config
from enron_case.context import StageContext
from enron_case.contracts import schemas
from enron_case.pseudo import pseudonymize
from enron_case.release import variants
from enron_case.risk import attack, aux_public, score, stage
from enron_case.synth import SynthOutput
from enron_case.synth.fixtures import fixture_pid
from enron_case.zones import Zone
from helpers import TEST_KEY_HEX, ctx_with_fixtures

# (context, risk_results, captured log lines) of one fixture run of the stage.
Outcome = tuple[StageContext, pl.DataFrame, list[str]]

CONFIG = Config()

INPUTS = (
    "snapshots",
    "events",
    "entities_p",
    "metric_series",
    "hypothesis_results",
    "address_map",
)


def fixture_context(synth: SynthOutput, root: Path, logs: list[str]) -> StageContext:
    ctx = ctx_with_fixtures("risk", synth, root, tables=INPUTS)
    ctx.log = logs.append
    return ctx


def truth_pids(synth: SynthOutput) -> tuple[dict[str, str], set[str]]:
    """From truth.json alone: address -> fixture pid, and the custodians' pids."""
    truth = synth.truth()
    entity_id = {e["truth_id"]: e["entity_id"] for e in truth["entities"] if e["entity_id"]}
    pid_of_address = {
        addr: fixture_pid(entity_id[tid])
        for addr, tid in truth["address_to_truth"].items()
        if tid in entity_id
    }
    custodians = {
        fixture_pid(e["entity_id"])
        for e in truth["entities"]
        if e["is_custodian"] and e["entity_id"]
    }
    return pid_of_address, custodians


@pytest.fixture(scope="module")
def outcome(synth: SynthOutput, tmp_path_factory: pytest.TempPathFactory) -> Outcome:
    logs: list[str] = []
    ctx = fixture_context(synth, tmp_path_factory.mktemp("risk"), logs)
    stage.run_with(ctx, risk_fakes.fixture_dependencies())
    return ctx, ctx.read("risk_results"), logs


def row(results: pl.DataFrame, variant: str, attacker: str) -> dict[str, Any]:
    return results.filter(
        (pl.col("release_variant") == variant) & (pl.col("attacker") == attacker)
    ).row(0, named=True)


def test_writes_one_valid_row_per_variant_and_attacker(outcome: Outcome) -> None:
    _, results, _ = outcome
    schemas.validate(results, "risk_results")
    pairs = results.select("release_variant", "attacker").rows()
    assert pairs == [(r, a) for r in ("R0", "R1", "R2") for a in ("A1", "A2")]


def test_reported_rates_equal_rates_from_ground_truth(outcome: Outcome, synth: SynthOutput) -> None:
    ctx, results, _ = outcome
    deps = risk_fakes.fixture_dependencies()
    r0 = deps.build_r0(ctx.read("snapshots"))
    aux = aux_public.load_aux_edges(ctx)
    pid_of_address, custodians = truth_pids(synth)
    targets = stage.node_level_persons(r0)
    seeds = score.Scorer.from_context(ctx, fixture_pid).seeds(custodians & targets, CONFIG.a2_seeds)
    for attacker, guesses, scored in (
        ("A1", attack.attack_a1(r0, aux, CONFIG.distance_chunk_rows), targets),
        ("A2", attack.attack_a2(r0, aux, seeds, CONFIG.a2_min_support), targets - set(seeds)),
    ):
        correct = sum(pid_of_address.get(guesses.get(p, "")) == p for p in scored)
        reported = row(results, "R0", attacker)
        assert reported["n_targets"] == len(scored)
        assert reported["reid_top1"] == pytest.approx(correct / len(scored))


def test_a1_reidentifies_most_active_custodians_in_r0(outcome: Outcome, synth: SynthOutput) -> None:
    ctx, results, _ = outcome
    r0 = variants.build_r0(ctx.read("snapshots"))
    guesses = attack.attack_a1(r0, aux_public.load_aux_edges(ctx), CONFIG.distance_chunk_rows)
    pid_of_address, custodians = truth_pids(synth)
    hits = sum(pid_of_address.get(guesses.get(p, "")) == p for p in custodians)
    assert hits / len(custodians) >= 0.9
    assert row(results, "R0", "A1")["reid_top1"] >= 0.8
    assert row(results, "R0", "A1")["unique_share"] >= 0.8


def test_aggregate_releases_give_nothing_to_match(outcome: Outcome) -> None:
    _, results, logs = outcome
    for variant in ("R1", "R2"):
        for attacker in ("A1", "A2"):
            reported = row(results, variant, attacker)
            assert reported["reid_top1"] == 0.0
            assert reported["unique_share"] == 0.0
            assert reported["median_anonymity_set"] >= 5
        assert any(f"{variant}: no person-level records" in line for line in logs)


def test_utility_on_planted_change(outcome: Outcome) -> None:
    _, results, _ = outcome
    assert row(results, "R0", "A1")["utility_effect_ratio"] == pytest.approx(1.0)
    assert row(results, "R1", "A1")["finding_survives"] is True  # fake R1 publishes all weeks
    r2 = row(results, "R2", "A1")
    assert r2["utility_effect_ratio"] is not None and r2["finding_survives"] is not None


def test_no_headline_means_utility_not_applicable(
    synth_nochange: SynthOutput, tmp_path: Path
) -> None:
    logs: list[str] = []
    ctx = fixture_context(synth_nochange, tmp_path, logs)
    stage.run_with(ctx, risk_fakes.fixture_dependencies())
    results = ctx.read("risk_results")
    assert results.get_column("utility_effect_ratio").null_count() == results.height
    assert results.get_column("finding_survives").null_count() == results.height


def test_logs_counts_only_and_writes_nothing_else(outcome: Outcome, synth: SynthOutput) -> None:
    ctx, _, logs = outcome
    names = synth.truth()["display_names"]
    for line in logs:
        assert "@" not in line and "p_" not in line
        assert not any(name.lower() in line.lower() for name in names)
    assert set(ctx.outputs) == {"risk_results"}


def test_r0_is_the_observed_snapshot_edges(synth: SynthOutput, tmp_path: Path) -> None:
    """R0 is attacked as published: persons absent from the observed-scope snapshots (for
    example, active only outside the analysis window) are not targets, even with events."""
    logs: list[str] = []
    ctx = fixture_context(synth, tmp_path, logs)
    snapshots = synth.table("snapshots")
    observed = snapshots.filter(pl.col("scope") == "observed")
    everyone = sorted(set(observed.get_column("src_pid")) | set(observed.get_column("dst_pid")))
    removed = everyone[:5]
    kept = snapshots.filter(~pl.col("src_pid").is_in(removed) & ~pl.col("dst_pid").is_in(removed))
    kept.write_parquet(ctx.path(Zone.RESTRICTED, schemas.table("snapshots").filename, "r"))
    kept_observed = kept.filter(pl.col("scope") == "observed")
    expected = set(kept_observed.get_column("src_pid")) | set(kept_observed.get_column("dst_pid"))
    assert expected.isdisjoint(removed)
    stage.run_with(ctx, risk_fakes.fixture_dependencies())
    assert row(ctx.read("risk_results"), "R0", "A1")["n_targets"] == len(expected)


def test_scorer_builds_the_keyed_pseudonym_function_itself(
    synth: SynthOutput, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without an injected pid function, the scorer loads the run key and maps an address to
    `person_pid(key, entity_id)`: a seed's address must belong to its own pseudonym."""
    monkeypatch.setenv(config.KEY_ENV, TEST_KEY_HEX)
    ctx = fixture_context(synth, tmp_path, [])
    amap = ctx.read("address_map")
    key = bytes.fromhex(TEST_KEY_HEX)
    entity = {a: e for a, e in amap.select("addr", "entity_id").iter_rows()}
    pids = {pseudonymize.person_pid(key, e) for e in entity.values()}
    seeds = score.Scorer.from_context(ctx).seeds(pids, 3)
    assert len(seeds) == 3
    assert all(pseudonymize.person_pid(key, entity[addr]) == pid for pid, addr in seeds.items())
