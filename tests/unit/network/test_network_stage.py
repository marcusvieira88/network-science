"""Stage run and planted-change acceptance on the synthetic corpus."""

from __future__ import annotations

import itertools
import math
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from enron_case.config import Config
from enron_case.contracts import vocab as v
from enron_case.network.communities import baseline_communities
from enron_case.network.metrics import compute_series
from enron_case.network.stage import run
from enron_case.synth import SynthOutput
from helpers import ctx_with_fixtures

SAMPLE_CONFIG = Config(internal_domain="acme-energy.com")
SHIFTED = ("indegree_gini", "cross_community_share")
# Welch t of (after − before): the planted step must stand out clearly; without a planted
# change the difference must not be significant at about the 5 % level.
PLANTED_MIN_T = 3.0
NO_CHANGE_MAX_T = 2.0


def default_series(synth: SynthOutput) -> pl.DataFrame:
    events, ents = synth.table("events"), synth.table("entities_p")
    comms = baseline_communities(events, ents, SAMPLE_CONFIG)
    return compute_series(events, ents, comms, SAMPLE_CONFIG)


def shift_t(series: pl.DataFrame, scope: str, metric: str, change: date) -> float:
    """Welch t of mean after the change week minus mean before it, over defined weeks."""
    rows = series.filter(
        (pl.col("scope") == scope) & (pl.col("metric") == metric) & pl.col("value").is_not_null()
    )
    after = rows.filter(pl.col("week") >= change).get_column("value").to_numpy()
    before = rows.filter(pl.col("week") < change).get_column("value").to_numpy()
    error = math.sqrt(after.var(ddof=1) / len(after) + before.var(ddof=1) / len(before))
    return float((after.mean() - before.mean()) / error)


@pytest.mark.parametrize(("scope", "metric"), list(itertools.product(v.SCOPES, SHIFTED)))
def test_planted_change_raises_concentration_and_crossing(
    synth: SynthOutput, synth_nochange: SynthOutput, scope: str, metric: str
) -> None:
    change = date.fromisoformat(synth.truth()["spec"]["change_week"])
    assert shift_t(default_series(synth), scope, metric, change) > PLANTED_MIN_T
    assert abs(shift_t(default_series(synth_nochange), scope, metric, change)) < NO_CHANGE_MAX_T


def test_baseline_communities_recover_planted_groups(synth: SynthOutput) -> None:
    got = baseline_communities(synth.table("events"), synth.table("entities_p"), SAMPLE_CONFIG)
    truth = dict(synth.table("communities").iter_rows())
    found = {pid: c for pid, c in got.iter_rows() if c >= 0}
    pairs = list(itertools.combinations(sorted(found), 2))
    agree = sum((found[a] == found[b]) == (truth[a] == truth[b]) for a, b in pairs)
    assert agree / len(pairs) >= 0.9


def test_series_is_deterministic(synth: SynthOutput) -> None:
    first = default_series(synth)
    for _ in range(3):
        assert default_series(synth).equals(first)


def test_stage_writes_contract_tables(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("network", synth, tmp_path, tables=("events", "entities_p"))
    run(ctx)
    assert ctx.read("snapshots").equals(synth.table("snapshots"))
    comms = ctx.read("communities")
    persons = synth.table("entities_p").filter(pl.col("type") == "person", pl.col("is_internal"))
    assert comms.get_column("pid").to_list() == persons.get_column("pid").to_list()
    series = ctx.read("metric_series")
    variants = {"default", *SAMPLE_CONFIG.sensitivity_variants}
    assert set(series.get_column("variant").to_list()) == variants
    weekly = series.filter(pl.col("variant") == "default")
    assert set(weekly.get_column("week").to_list()) == set(
        synth.table("metric_series").get_column("week").to_list()
    )
    assert set(ctx.outputs) == {"snapshots", "communities", "metric_series"}
