"""S6: test H1–H4 on the metric series and write `hypothesis_results`."""

from __future__ import annotations

import importlib

from enron_case.context import StageContext
from enron_case.finding import artifacts, hypotheses, select
from enron_case.finding.hypotheses import Network, Recompute

# WP-E's public recompute function (docs/agents/WP-E.md). Resolved at run time because WP-E is
# built in parallel; once merged, this can become a plain import.
RECOMPUTE_MODULE = "enron_case.network.metrics"
RECOMPUTE_FUNCTION = "compute_series"


def run(ctx: StageContext) -> None:
    run_with(ctx, _network_recompute())


def run_with(ctx: StageContext, recompute: Recompute) -> None:
    network = Network(ctx.read("events"), ctx.read("entities_p"), ctx.read("communities"))
    evidence = hypotheses.gather(ctx.read("metric_series"), network, recompute, ctx.config)
    checks = artifacts.run_checks(evidence, network, recompute, ctx.config)
    ctx.write("artifact_results", artifacts.table(checks))
    failed = frozenset(artifacts.failed(checks))
    table = ctx.write("hypothesis_results", select.results_table(evidence, failed))
    supported = table.filter(table["supported"] == select.YES).height
    ctx.log(
        f"[finding] {table.height} hypotheses tested, {supported} supported, "
        f"{len(failed)} failed an artifact check"
    )


def _network_recompute() -> Recompute:
    recompute: Recompute = getattr(importlib.import_module(RECOMPUTE_MODULE), RECOMPUTE_FUNCTION)
    return recompute
