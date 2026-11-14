"""Support, confidence and headline rules of docs/hypotheses.md, and the results table."""

from __future__ import annotations

import math
from collections.abc import Sequence

import polars as pl
from scipy.stats import norm

from enron_case.contracts import schemas
from enron_case.finding import stats
from enron_case.finding.hypotheses import Evidence

YES, NO, INCONCLUSIVE = "yes", "no", "inconclusive"
HIGH, MODERATE, LOW = "high", "moderate", "low"
# One-sided, because every hypothesis states its direction in advance.
NULL_Z_CRITICAL = float(norm.ppf(1.0 - stats.ALPHA))

Checks = tuple[bool, bool, bool]  # null model, leave-one-mailbox-out, variants


def support(direction: int, p_holm: float, ci_low: float, ci_high: float) -> str:
    """yes / no / inconclusive from the corrected p-value and the effect interval."""
    if math.isnan(ci_low) or math.isnan(ci_high):
        return INCONCLUSIVE
    if stats.on_side(-direction, ci_low, ci_high):
        return NO
    significant = p_holm < stats.ALPHA
    on_side = stats.on_side(direction, ci_low, ci_high)
    if significant and on_side:
        return YES
    if not significant and not on_side:
        return NO
    return INCONCLUSIVE


def robustness_checks(evidence: Evidence) -> Checks:
    d = evidence.hypothesis.direction
    null_pass = d * evidence.null_z > NULL_Z_CRITICAL
    loo_pass = bool(evidence.loo_effects) and all(d * e > 0 for e in evidence.loo_effects)
    variants_pass = 0 < evidence.variants_total == evidence.variants_passed
    return null_pass, loo_pass, variants_pass


def confidence(supported: str, checks: Checks) -> str:
    if supported != YES:
        return LOW
    failed = checks.count(False)
    if failed == 0:
        return HIGH
    return MODERATE if failed == 1 else LOW


def _headline(evidence: Sequence[Evidence], supported: Sequence[str]) -> int | None:
    """Index of the supported hypothesis with the largest effect in its direction."""
    candidates = [
        (-e.hypothesis.direction * e.effect, index)
        for index, (e, s) in enumerate(zip(evidence, supported, strict=True))
        if s == YES
    ]
    return min(candidates)[1] if candidates else None


def _loo_range(effects: tuple[float, ...]) -> tuple[float, float]:
    """Min and max leave-one-out effect; NaN when none, or any, is undefined."""
    if not effects or any(math.isnan(e) for e in effects):
        return math.nan, math.nan
    return min(effects), max(effects)


def results_table(evidence: Sequence[Evidence]) -> pl.DataFrame:
    """The `hypothesis_results` table: one row per hypothesis, at most one headline."""
    p_holm = stats.holm([e.p_perm for e in evidence])
    supported = [
        support(e.hypothesis.direction, p, e.ci_low, e.ci_high)
        for e, p in zip(evidence, p_holm, strict=True)
    ]
    headline = _headline(evidence, supported)
    rows = []
    for index, (e, p, s) in enumerate(zip(evidence, p_holm, supported, strict=True)):
        loo_min, loo_max = _loo_range(e.loo_effects)
        rows.append(
            {
                "hypothesis": e.hypothesis.id,
                "metric": e.hypothesis.metric,
                "scope": e.hypothesis.scope,
                "change_week": e.change_week if p < stats.ALPHA else None,
                "p_perm": e.p_perm,
                "p_holm": p,
                "effect": e.effect,
                "ci_low": e.ci_low,
                "ci_high": e.ci_high,
                "null_z": e.null_z,
                "loo_min_effect": loo_min,
                "loo_max_effect": loo_max,
                "robust_variants_passed": e.variants_passed,
                "robust_variants_total": e.variants_total,
                "supported": s,
                "confidence": confidence(s, robustness_checks(e)),
                "is_headline": index == headline,
            }
        )
    spec = schemas.table("hypothesis_results")
    return schemas.conform(pl.DataFrame(rows, schema=spec.polars_schema), spec.name)
