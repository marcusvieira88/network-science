"""Support, confidence and headline rules (docs/hypotheses.md) on hand-built evidence."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date

import pytest

from enron_case.config import Config
from enron_case.contracts import schemas
from enron_case.contracts import vocab as v
from enron_case.finding import select
from enron_case.finding.hypotheses import HYPOTHESES, Evidence

CONFIG = Config()

NAN = math.nan
WEEK = date(2001, 8, 13)


def _evidence(index: int, **changes: object) -> Evidence:
    """Evidence that passes everything, in the hypothesised direction."""
    hyp = HYPOTHESES[index]
    d = hyp.direction
    base = Evidence(
        hypothesis=hyp,
        change_week=WEEK,
        p_perm=0.001,
        effect=2.0 * d,
        ci_low=1.0 if d > 0 else -3.0,
        ci_high=3.0 if d > 0 else -1.0,
        null_z=3.0 * d,
        loo_effects=(1.5 * d, 2.5 * d),
        variants_passed=2,
        variants_total=2,
    )
    return replace(base, **changes)  # type: ignore[arg-type]  # overrides of mixed Evidence fields


def _all(**changes: object) -> list[Evidence]:
    return [_evidence(i, **changes) for i in range(len(HYPOTHESES))]


def test_hypotheses_are_bound_as_pre_stated() -> None:
    bound = [(h.id, h.metric, h.scope, h.direction) for h in HYPOTHESES]
    assert bound == [
        ("H1", "indegree_gini", "core", 1),
        ("H2", "cross_community_share", "observed", 1),
        ("H3", "external_share", "observed", -1),
        ("H4", "tie_turnover", "core", 1),
    ]


@pytest.mark.parametrize(
    ("direction", "p_holm", "ci", "expected"),
    [
        (1, 0.01, (0.5, 2.0), "yes"),
        (-1, 0.01, (-2.0, -0.5), "yes"),
        (1, 0.01, (-0.5, 2.0), "inconclusive"),  # test passes, interval includes 0
        (1, 0.20, (0.5, 2.0), "inconclusive"),  # interval passes, test does not
        (1, 0.20, (-0.5, 2.0), "no"),
        (1, 0.01, (-2.0, -0.5), "no"),  # wholly on the wrong side
        (-1, 0.01, (0.5, 2.0), "no"),
        (1, 1.0, (NAN, NAN), "inconclusive"),  # effect not computable
    ],
)
def test_support_rule(
    direction: int, p_holm: float, ci: tuple[float, float], expected: str
) -> None:
    assert select.support(direction, p_holm, *ci, CONFIG.alpha) == expected


@pytest.mark.parametrize(
    ("supported", "checks", "expected"),
    [
        ("yes", (True, True, True), "high"),
        ("yes", (False, True, True), "moderate"),
        ("yes", (True, True, False), "moderate"),
        ("yes", (False, False, True), "low"),
        ("no", (True, True, True), "low"),
        ("inconclusive", (True, True, True), "low"),
    ],
)
def test_confidence_rule(supported: str, checks: tuple[bool, bool, bool], expected: str) -> None:
    assert select.confidence(supported, checks) == expected


def test_robustness_checks_respect_direction() -> None:
    down = _evidence(2)
    assert select.robustness_checks(down, CONFIG.alpha) == (True, True, True)
    assert select.robustness_checks(replace(down, null_z=1.0), CONFIG.alpha) == (False, True, True)
    assert select.robustness_checks(replace(down, loo_effects=(-1.0, 0.2)), CONFIG.alpha) == (
        True,
        False,
        True,
    )
    assert select.robustness_checks(replace(down, variants_passed=1), CONFIG.alpha) == (
        True,
        True,
        False,
    )


def test_null_check_is_one_sided_at_alpha() -> None:
    up = _evidence(0)
    assert select.robustness_checks(replace(up, null_z=1.6), CONFIG.alpha)[0] is False
    assert select.robustness_checks(replace(up, null_z=1.7), CONFIG.alpha)[0] is True


def test_no_variants_is_not_a_pass() -> None:
    up = _evidence(0, variants_passed=0, variants_total=0)
    assert select.robustness_checks(up, CONFIG.alpha)[2] is False


def test_uncomputable_loo_fails_the_check() -> None:
    assert select.robustness_checks(_evidence(0, loo_effects=(1.0, NAN)), CONFIG.alpha)[1] is False


def test_table_has_four_rows_and_validates() -> None:
    table = select.results_table(_all(), CONFIG)
    schemas.validate(table, "hypothesis_results")
    assert table.get_column("hypothesis").to_list() == list(v.HYPOTHESES)
    assert set(table.get_column("supported")) <= set(v.SUPPORT)
    assert set(table.get_column("confidence")) <= set(v.CONFIDENCE)


def test_table_applies_holm_to_p_perm() -> None:
    p = [0.01, 0.04, 0.03, 0.005]
    evidence = [replace(e, p_perm=pi) for e, pi in zip(_all(), p, strict=True)]
    table = select.results_table(evidence, CONFIG)
    assert table.get_column("p_holm").to_list() == pytest.approx([0.03, 0.06, 0.06, 0.02])
    # H2 and H3 no longer significant after correction; intervals still on the right side
    assert table.get_column("supported").to_list() == ["yes", "inconclusive", "inconclusive", "yes"]
    assert table.get_column("change_week").to_list() == [WEEK, None, None, WEEK]


def test_headline_is_largest_effect_in_hypothesised_direction() -> None:
    evidence = _all()
    evidence[2] = replace(evidence[2], effect=-5.0)  # H3 is "down": 5 in its direction
    table = select.results_table(evidence, CONFIG)
    assert table.get_column("is_headline").to_list() == [False, False, True, False]


def test_headline_ties_go_to_lower_id() -> None:
    table = select.results_table(_all(), CONFIG)
    assert table.get_column("is_headline").to_list() == [True, False, False, False]


def test_headline_only_among_supported() -> None:
    evidence = _all()
    evidence[0] = replace(evidence[0], effect=9.0, ci_low=-1.0)  # largest, but not supported
    table = select.results_table(evidence, CONFIG)
    assert table.get_column("is_headline").to_list() == [False, True, False, False]


def test_headline_requires_every_robustness_check() -> None:
    """Research R10: a supported hypothesis that fails a robustness check cannot be headline."""
    evidence = _all()
    evidence[0] = replace(evidence[0], effect=9.0, null_z=0.0)  # largest, supported, null fails
    table = select.results_table(evidence, CONFIG)
    assert table.get_column("supported").to_list()[0] == "yes"
    assert table.get_column("confidence").to_list()[0] == "moderate"
    assert table.get_column("is_headline").to_list() == [False, True, False, False]


def test_no_high_confidence_means_no_headline() -> None:
    table = select.results_table(_all(null_z=0.0), CONFIG)
    assert set(table.get_column("supported")) == {"yes"}
    assert not any(table.get_column("is_headline"))


def test_none_supported_has_no_headline() -> None:
    table = select.results_table(_all(p_perm=0.5), CONFIG)
    assert table.get_column("supported").to_list() == ["inconclusive"] * 4
    assert not any(table.get_column("is_headline"))
    assert set(table.get_column("confidence")) == {"low"}


def test_loo_range_is_reported() -> None:
    table = select.results_table(_all(loo_effects=(0.5, 3.0, 1.0)), CONFIG)
    assert table.get_column("loo_min_effect").to_list()[0] == 0.5
    assert table.get_column("loo_max_effect").to_list()[0] == 3.0
