"""The finding stage on the synthetic fixtures, with the WP-E recompute replaced by a fake."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from enron_case.config import Config
from enron_case.contracts import schemas
from enron_case.finding import hypotheses, stage
from enron_case.synth import SynthOutput
from helpers import ctx_with_fixtures

INPUTS = ("metric_series", "events", "entities_p", "communities")


@dataclass
class FakeRecompute:
    """Returns the fixture series unchanged, so leave-one-out effects equal the full effect
    and the null reproduces it exactly. Records every call."""

    series: pl.DataFrame
    calls: list[tuple[str, frozenset[str], int]] = field(default_factory=list)

    def __call__(
        self,
        events: pl.DataFrame,
        entities_p: pl.DataFrame,
        communities: pl.DataFrame,
        config: Config,
        variant: str = "default",
        exclude_pids: frozenset[str] = frozenset(),
    ) -> pl.DataFrame:
        self.calls.append((variant, exclude_pids, events.height))
        return self.series.filter(pl.col("variant") == variant)


def _run(fixture: SynthOutput, root: Path) -> tuple[pl.DataFrame, FakeRecompute]:
    ctx = ctx_with_fixtures("finding", fixture, root, tables=INPUTS)
    fake = FakeRecompute(fixture.table("metric_series"))
    stage.run_with(ctx, fake)
    return ctx.read("hypothesis_results"), fake


@pytest.fixture(scope="module")
def planted(synth: SynthOutput, tmp_path_factory: pytest.TempPathFactory) -> pl.DataFrame:
    return _run(synth, tmp_path_factory.mktemp("planted"))[0]


@pytest.fixture(scope="module")
def nochange(synth_nochange: SynthOutput, tmp_path_factory: pytest.TempPathFactory) -> pl.DataFrame:
    return _run(synth_nochange, tmp_path_factory.mktemp("nochange"))[0]


def test_planted_change_supports_h1_and_h2(planted: pl.DataFrame) -> None:
    schemas.validate(planted, "hypothesis_results")
    supported = dict(zip(planted["hypothesis"], planted["supported"], strict=True))
    assert supported["H1"] == "yes"
    assert supported["H2"] == "yes"
    assert supported["H3"] != "yes"
    assert supported["H4"] != "yes"


def test_planted_change_week_is_found(synth: SynthOutput, planted: pl.DataFrame) -> None:
    weeks = planted.filter(pl.col("supported") == "yes").get_column("change_week").to_list()
    assert len(weeks) == 2
    planted_week = date.fromisoformat(synth.truth()["spec"]["change_week"])
    assert all(abs((week - planted_week).days) <= 7 for week in weeks)


def test_no_headline_when_planted_effects_are_only_moderate(planted: pl.DataFrame) -> None:
    # The fake recompute caps confidence at moderate (see the next test), and research R10
    # admits only hypotheses that pass every robustness check as headline. The end-to-end
    # sample run, with the real recompute, does produce a high-confidence headline.
    assert not any(planted.get_column("is_headline"))


def test_fake_null_reproduces_effect_so_confidence_is_capped(planted: pl.DataFrame) -> None:
    rows = planted.filter(pl.col("supported") == "yes")
    assert rows.get_column("null_z").to_list() == [0.0, 0.0]
    assert rows.get_column("loo_min_effect").to_list() == rows.get_column("effect").to_list()
    assert rows.get_column("robust_variants_total").to_list() == [1, 1]
    assert rows.get_column("robust_variants_passed").to_list() == [1, 1]
    assert rows.get_column("confidence").to_list() == ["moderate", "moderate"]


def test_no_change_supports_nothing(nochange: pl.DataFrame) -> None:
    schemas.validate(nochange, "hypothesis_results")
    assert nochange.height == 4
    assert "yes" not in nochange.get_column("supported").to_list()
    assert not any(nochange.get_column("is_headline"))


def test_recompute_called_per_custodian_and_null_replicate(
    synth: SynthOutput, tmp_path: Path
) -> None:
    _, fake = _run(synth, tmp_path)
    custodians = set(
        synth.table("entities_p").filter(pl.col("is_custodian")).get_column("pid").to_list()
    )
    loo = [excluded for _variant, excluded, _n in fake.calls if excluded]
    assert sorted(loo, key=sorted) == sorted(({p} for p in custodians), key=sorted)
    null = [call for call in fake.calls if not call[1]]
    # The null replicates, plus one recompute for the H2 baseline placebo (artifacts.py).
    assert len(null) == hypotheses.NULL_REPLICATES + 1
    assert {variant for variant, _e, _n in fake.calls} == {"default"}


def test_stage_is_deterministic(synth: SynthOutput, tmp_path: Path) -> None:
    first, _ = _run(synth, tmp_path / "a")
    second, _ = _run(synth, tmp_path / "b")
    assert first.equals(second)
