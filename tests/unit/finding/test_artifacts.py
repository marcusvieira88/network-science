"""Artifact checks (finding/artifacts.py) on synthetic data with known structure."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from enron_case.config import Config
from enron_case.contracts import schemas
from enron_case.finding import artifacts, select
from enron_case.finding.hypotheses import HYPOTHESES, Evidence, Network
from enron_case.network.communities import baseline_communities
from enron_case.network.metrics import compute_series
from enron_case.synth import SynthOutput

CONFIG = Config(internal_domain="acme-energy.com", bootstrap_reps=200)


def _network(synth: SynthOutput) -> Network:
    events, entities = synth.table("events"), synth.table("entities_p")
    return Network(events, entities, baseline_communities(events, entities, CONFIG))


def test_placebo_passes_when_groups_do_not_drift(synth: SynthOutput) -> None:
    """The generator's communities never change, so a calm out-of-sample half-year is flat."""
    check = artifacts.baseline_placebo(_network(synth), compute_series, CONFIG)
    assert check.passes is True
    assert abs(check.statistic) <= artifacts.PLACEBO_MAX_EFFECT


def test_placebo_fails_on_a_jump_right_after_the_fitting_period(synth: SynthOutput) -> None:
    """A recompute whose cross-community share jumps in the second half of the baseline year
    (what stale groups produce) must fail the placebo."""

    def drifting(*args: object, **kwargs: object) -> pl.DataFrame:
        series = compute_series(*args, **kwargs)  # type: ignore[arg-type]
        jump = pl.col("week") > date(2000, 7, 1)
        return series.with_columns(
            pl.when((pl.col("metric") == "cross_community_share") & jump)
            .then(pl.col("value") + 0.3)
            .otherwise(pl.col("value"))
            .alias("value")
        )

    check = artifacts.baseline_placebo(_network(synth), drifting, CONFIG)
    assert check.passes is False


def test_within_custodian_sees_a_behavioural_shift(synth: SynthOutput) -> None:
    """In the planted world custodians themselves mail outward less after the change week."""
    check = artifacts.within_custodian(_network(synth), date(2001, 8, 13), CONFIG)
    assert check.n_units >= CONFIG.k_min
    assert check.passes is True
    assert check.ci_high < 0


def test_within_custodian_without_change_point_is_not_run(synth: SynthOutput) -> None:
    check = artifacts.within_custodian(_network(synth), None, CONFIG)
    assert check.passes is None


def _evidence() -> list[Evidence]:
    out = []
    for hyp in HYPOTHESES:
        d = hyp.direction
        out.append(
            Evidence(
                hyp,
                date(2001, 8, 13),
                0.001,
                2.0 * d,
                1.0 if d > 0 else -3.0,
                3.0 if d > 0 else -1.0,
                3.0 * d,
                (1.5 * d, 2.5 * d),
                2,
                2,
            )
        )
    out[1] = replace(out[1], effect=9.0)  # H2: the largest effect
    return out


def test_failed_artifact_check_caps_confidence_and_blocks_headline() -> None:
    clean = select.results_table(_evidence())
    assert clean.filter(pl.col("is_headline")).get_column("hypothesis").to_list() == ["H2"]
    capped = select.results_table(_evidence(), frozenset({"H2"}))
    h2 = capped.filter(pl.col("hypothesis") == "H2").row(0, named=True)
    assert h2["supported"] == "yes"
    assert h2["confidence"] == "low"
    assert not h2["is_headline"]
    assert capped.filter(pl.col("is_headline")).get_column("hypothesis").to_list() == ["H1"]


def test_table_matches_contract(synth: SynthOutput, tmp_path: Path) -> None:
    checks = artifacts.run_checks(_evidence(), _network(synth), compute_series, CONFIG)
    schemas.validate(
        schemas.conform(artifacts.table(checks), "artifact_results"), "artifact_results"
    )


def test_within_custodian_is_independent_of_row_order(synth: SynthOutput) -> None:
    network = _network(synth)
    shuffled = Network(
        network.events.sample(fraction=1.0, shuffle=True, seed=3),
        network.entities_p,
        network.communities,
    )
    first = artifacts.within_custodian(network, date(2001, 8, 13), CONFIG)
    second = artifacts.within_custodian(shuffled, date(2001, 8, 13), CONFIG)
    # Shuffling changes float summation order (last-bit noise); the custodians resampled by
    # the seeded bootstrap must not change, so the interval agrees to rounding.
    assert (first.n_units, first.passes) == (second.n_units, second.passes)
    for field in ("statistic", "ci_low", "ci_high"):
        assert getattr(first, field) == pytest.approx(getattr(second, field), rel=1e-9)
