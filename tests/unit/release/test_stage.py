"""T074: the release stage writes every published table, through kanon, from fixtures."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from enron_case.context import StageContext
from enron_case.contracts import schemas
from enron_case.errors import ContractViolation
from enron_case.release import stage
from enron_case.synth import SynthOutput
from enron_case.zones import Zone
from helpers import ctx_with_fixtures

INPUTS = (
    "metric_series",
    "hypothesis_results",
    "risk_results",
    "artifact_results",
    "exploratory_results",
    "profile_results",
    "departure_results",
    "departure_test_results",
    "snapshots",
    "communities",
    "events",
    "entities_p",
)
RELEASE_TABLES = (
    "data_quality",
    "header_fields",
    "weekly_metrics",
    "hypotheses",
    "risk",
    "degree_distribution",
    "community_graph",
    "community_groups",
    "artifact_checks",
    "exploratory",
    "record_profile",
    "departures",
    "departure_tests",
)
EXACT = (
    "data_quality",
    "header_fields",
    "weekly_metrics",
    "hypotheses",
    "risk",
    "community_graph",
    "community_groups",
)


@pytest.fixture
def ran(synth: SynthOutput, tmp_path: Path) -> StageContext:
    ctx = ctx_with_fixtures("release", synth, tmp_path, tables=INPUTS)
    stage.run(ctx)
    return ctx


def test_writes_exactly_the_release_tables(ran: StageContext) -> None:
    release_dir = ran.paths.dir(Zone.RELEASE)
    written = sorted(p.name for p in release_dir.iterdir())
    assert written == sorted(schemas.table(n).filename for n in RELEASE_TABLES)
    assert set(ran.outputs) == set(RELEASE_TABLES)


@pytest.mark.parametrize("name", EXACT)
def test_table_equals_release_fixture(ran: StageContext, synth: SynthOutput, name: str) -> None:
    assert_frame_equal(ran.read(name), synth.table(name), check_exact=False)


def test_degree_distribution_is_consistent_with_fixture(
    ran: StageContext, synth: SynthOutput
) -> None:
    got, ref = ran.read("degree_distribution"), synth.table("degree_distribution")
    assert set(got["degree_bucket"]) == set(ref["degree_bucket"])
    assert set(ref["period"]) <= set(got["period"])
    assert (got["persons"].drop_nulls() >= ran.config.k_min).all()


def test_nothing_written_contains_an_identifier(ran: StageContext) -> None:
    for path in ran.paths.dir(Zone.RELEASE).iterdir():
        text = path.read_text(encoding="utf-8")
        assert "@" not in text
        assert not pl.Series([text]).str.contains(r"[po]_[a-z2-7]{16}").any(), path.name


def test_missing_counts_fail_loudly(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("release", synth, tmp_path, tables=INPUTS)
    (ctx.paths.dir(Zone.COUNTS) / "clean_counts.json").unlink()
    with pytest.raises(ContractViolation, match="'clean_counts' have not been produced"):
        stage.run(ctx)


def test_manual_review_counts_are_optional(ran: StageContext) -> None:
    # The fixtures hold no manual review, and the release stage ran without it.
    assert ran.read_optional_counts("identity_manual") is None
    assert "data_quality" in ran.outputs
