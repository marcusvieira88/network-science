"""S6: test H1–H4 and H5–H25, run the artifact checks, profile the record by month, and test
H26 (custodian departures)."""

from __future__ import annotations

import polars as pl

from enron_case.context import StageContext
from enron_case.finding import artifacts, departures, exploratory, hypotheses, profile, select
from enron_case.finding.hypotheses import Network, Recompute
from enron_case.network.metrics import compute_series


def run(ctx: StageContext) -> None:
    run_with(ctx, compute_series)


def run_with(ctx: StageContext, recompute: Recompute) -> None:
    network = Network(ctx.read("events"), ctx.read("entities_p"), ctx.read("communities"))
    evidence = hypotheses.gather(ctx.read("metric_series"), network, recompute, ctx.config)
    checks = artifacts.run_checks(evidence, network, recompute, ctx.config)
    ctx.write("artifact_results", artifacts.table(checks))
    failed = frozenset(artifacts.failed(checks))
    table = ctx.write("hypothesis_results", select.results_table(evidence, ctx.config, failed))
    custodians = exploratory.custodian_tables(network.events, network.entities_p)
    explored = ctx.write("exploratory_results", exploratory.run_family_on(custodians, ctx.config))
    ctx.write("profile_results", profile.monthly_profile(custodians, ctx.config))
    left = departures.departure_tables(network.events, network.entities_p, ctx.config)
    ctx.write("departure_results", left.periods)
    tests = ctx.write("departure_test_results", left.tests)
    outcome = tests.filter(pl.col("variant") == departures.PRIMARY).get_column("outcome").item()
    ctx.log(f"[finding] H26 custodian departures: {outcome}")
    confident = explored.filter(explored["outcome"] == exploratory.CONFIDENT).height
    ctx.log(f"[finding] hypotheses H5-H{4 + explored.height}: {confident} held true")
    supported = table.filter(table["supported"] == select.YES).height
    ctx.log(
        f"[finding] {table.height} hypotheses tested, {supported} supported, "
        f"{len(failed)} failed or could not run an artifact check"
    )
