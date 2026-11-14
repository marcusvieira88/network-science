"""S6: test H1–H4 on the metric series and write `hypothesis_results`."""

from __future__ import annotations

from enron_case.context import StageContext
from enron_case.finding import artifacts, exploratory, hypotheses, select
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
    explored = ctx.write(
        "exploratory_results",
        exploratory.run_family(network.events, network.entities_p, ctx.config),
    )
    confident = explored.filter(explored["outcome"] == exploratory.CONFIDENT).height
    ctx.log(f"[finding] hypotheses H5-H{4 + explored.height}: {confident} held true")
    supported = table.filter(table["supported"] == select.YES).height
    ctx.log(
        f"[finding] {table.height} hypotheses tested, {supported} supported, "
        f"{len(failed)} failed or could not run an artifact check"
    )
