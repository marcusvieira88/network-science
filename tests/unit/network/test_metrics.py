"""Each metric against hand-computed toy graphs (docs/metrics.md)."""

from __future__ import annotations

import itertools
from datetime import date

import polars as pl
import pytest

from enron_case.config import Config
from enron_case.contracts import schemas
from enron_case.contracts import vocab as v
from enron_case.errors import UsageError
from enron_case.network.communities import baseline_communities
from enron_case.network.metrics import compute_series
from network_toys import (
    WEEK_1,
    WEEK_2,
    WEEK_3,
    Mailbag,
    Person,
    communities,
    entities,
    people,
    toy_config,
)

Key = tuple[str, str, date]


def series(
    bag: Mailbag,
    persons: list[Person],
    config: Config,
    groups: dict[Person, int] | None = None,
    variant: str = "default",
    exclude: frozenset[str] = frozenset(),
) -> dict[Key, tuple[float | None, int]]:
    comms = communities(groups or {p: 0 for p in persons})
    out = compute_series(bag.events(), entities(persons), comms, config, variant, exclude)
    schemas.validate(schemas.conform(out, "metric_series"), "metric_series")
    assert set(out.get_column("variant").to_list()) == {variant}
    return {
        (scope, metric, week): (value, n_active)
        for scope, week, metric, value, n_active in out.select(
            "scope", "week", "metric", "value", "n_active"
        ).iter_rows()
    }


def values(result: dict[Key, tuple[float | None, int]], week: date = WEEK_1) -> dict[str, object]:
    return {metric: result[("observed", metric, week)][0] for metric in v.METRICS}


def complete_graph(bag: Mailbag, group: list[Person], week: date = WEEK_1) -> None:
    for sender, recipient in itertools.permutations(group, 2):
        bag.send(sender, [recipient], week=week)


# ---- empty and undefined -------------------------------------------------------------------


def test_empty_graph_gives_null_rows_for_every_week() -> None:
    a, b = people("a", "b")
    result = series(Mailbag(), [a, b], toy_config(weeks=2))
    assert len(result) == len(v.SCOPES) * len(v.METRICS) * 2
    assert all(value is None and n_active == 0 for value, n_active in result.values())


def test_fewer_than_k_active_gives_null_not_zero() -> None:
    group = people("a", "b", "c", "d")
    bag = Mailbag()
    complete_graph(bag, group)
    result = series(bag, group, toy_config(k_min=5))
    assert all(value is None for value in values(result).values())
    assert result[("observed", "volume", WEEK_1)] == (None, 4)


# ---- complete graph ------------------------------------------------------------------------


def test_complete_graph() -> None:
    group = people("a", "b", "c", "d", "e")
    bag = Mailbag()
    complete_graph(bag, group, WEEK_1)
    complete_graph(bag, group, WEEK_2)
    groups = {p: (0 if i < 3 else 1) for i, p in enumerate(group)}
    result = series(bag, group, toy_config(weeks=2), groups)
    got = values(result)
    assert got["volume"] == 20
    assert got["active_persons"] == 5
    assert got["density"] == pytest.approx(1.0)
    assert got["reciprocity"] == pytest.approx(1.0)
    assert got["indegree_gini"] == pytest.approx(0.0)
    assert got["cross_community_share"] == pytest.approx(12 / 20)
    assert got["external_share"] == pytest.approx(0.0)
    assert got["tie_turnover"] is None  # first week has no previous week
    assert values(result, WEEK_2)["tie_turnover"] == pytest.approx(0.0)
    assert result[("observed", "density", WEEK_1)][1] == 5


# ---- star ----------------------------------------------------------------------------------


def test_star_into_centre() -> None:
    centre, *leaves = people("hub", "l1", "l2", "l3", "l4", "l5")
    bag = Mailbag()
    for leaf in leaves:
        bag.send(leaf, [centre])
    got = values(series(bag, [centre, *leaves], toy_config()))
    n = 6
    assert got["volume"] == 5
    assert got["active_persons"] == n
    assert got["density"] == pytest.approx(1 / n)
    assert got["reciprocity"] == pytest.approx(0.0)
    assert got["indegree_gini"] == pytest.approx((n - 1) / n)
    assert got["cross_community_share"] == pytest.approx(0.0)


# ---- two cliques ---------------------------------------------------------------------------


def test_two_cliques_with_one_bridge_in_second_week() -> None:
    left = people("a", "b", "c")
    right = people("d", "e", "f")
    bag = Mailbag()
    for week in (WEEK_1, WEEK_2):
        complete_graph(bag, left, week)
        complete_graph(bag, right, week)
    bag.send(left[0], [right[0]], week=WEEK_2)
    groups = {**{p: 0 for p in left}, **{p: 1 for p in right}}
    result = series(bag, left + right, toy_config(weeks=2), groups)
    first, second = values(result, WEEK_1), values(result, WEEK_2)
    assert first["density"] == pytest.approx(12 / 30)
    assert first["reciprocity"] == pytest.approx(1.0)
    assert first["cross_community_share"] == pytest.approx(0.0)
    assert second["cross_community_share"] == pytest.approx(1 / 13)
    assert second["reciprocity"] == pytest.approx(12 / 13)
    assert second["tie_turnover"] == pytest.approx(1 - 12 / 13)


def test_unassigned_persons_left_out_of_cross_community_share() -> None:
    left = people("a", "b", "c")
    newcomer, other = people("n", "o")
    bag = Mailbag()
    complete_graph(bag, left)
    bag.send(left[0], [newcomer, other])
    groups = {**{p: 0 for p in left}, newcomer: -1, other: 1}
    got = values(series(bag, [*left, newcomer, other], toy_config(), groups))
    # assigned weight: 6 clique ties of 1 and a→o of 1/2; crossing: a→o.
    assert got["cross_community_share"] == pytest.approx(0.5 / 6.5)


# ---- weighted in-degree Gini ---------------------------------------------------------------


def test_gini_of_weighted_indegree() -> None:
    a, b, c, d, e = people("a", "b", "c", "d", "e")
    bag = Mailbag()
    bag.send(a, [c, d])  # 1/2 each
    bag.send(a, [c, d])
    bag.send(b, [e])
    bag.send(c, [e])
    # in-degrees: a 0, b 0, c 1, d 1, e 2 → Σ|xi−xj| / (2 n² mean) = 20 / 40
    got = values(series(bag, [a, b, c, d, e], toy_config()))
    assert got["indegree_gini"] == pytest.approx(0.5)
    assert got["volume"] == 4


# ---- external share and scopes -------------------------------------------------------------


def test_external_share_by_scope() -> None:
    c1, c2, c3, c4, c5 = people("c1", "c2", "c3", "c4", "c5", custodian=True)
    plain = Person("plain")
    outsider = Person("x", internal=False)
    insiders = [c1, c2, c3, c4, c5, plain]
    bag = Mailbag()
    complete_graph(bag, [c1, c2, c3, c4, c5])  # 20 ties of weight 1 among custodians
    bag.send(c1, [outsider, c2])  # 1/2 external, 1/2 internal
    bag.send(plain, [outsider])  # 1 external, from a non-custodian
    bag.send(outsider, [c1])  # external sender: not counted
    result = series(bag, [*insiders, outsider], toy_config())
    assert result[("observed", "external_share", WEEK_1)][0] == pytest.approx(1.5 / 22)
    assert result[("core", "external_share", WEEK_1)][0] == pytest.approx(0.5 / 21)
    assert result[("core", "active_persons", WEEK_1)] == (5.0, 5)
    assert result[("observed", "active_persons", WEEK_1)] == (5.0, 5)


def test_core_scope_uses_custodian_ties_only() -> None:
    custodians = people("c1", "c2", "c3", "c4", "c5", custodian=True)
    plain = people("p1", "p2")
    bag = Mailbag()
    complete_graph(bag, custodians)
    for p in plain:
        bag.send(p, [custodians[0]])
    result = series(bag, custodians + plain, toy_config())
    assert result[("core", "density", WEEK_1)][0] == pytest.approx(1.0)
    assert result[("observed", "density", WEEK_1)][0] == pytest.approx(22 / 42)


def test_non_person_and_out_of_network_events_ignored() -> None:
    group = people("a", "b", "c", "d", "e")
    mailing_list = Person("list", type="list")
    bag = Mailbag()
    complete_graph(bag, group)
    bag.send(group[0], [mailing_list])
    bag.send(mailing_list, group)
    bag.send(group[0], [group[1]], in_network=False)
    got = values(series(bag, [*group, mailing_list], toy_config()))
    assert got["volume"] == 20
    assert got["density"] == pytest.approx(1.0)


# ---- tie turnover --------------------------------------------------------------------------


def test_turnover_null_after_undefined_week() -> None:
    group = people("a", "b", "c", "d", "e")
    bag = Mailbag()
    complete_graph(bag, group, WEEK_1)
    bag.send(group[0], [group[1]], week=WEEK_2)  # 2 active persons: undefined
    complete_graph(bag, group, WEEK_3)
    result = series(bag, group, toy_config(weeks=3))
    assert values(result, WEEK_2)["tie_turnover"] is None
    assert values(result, WEEK_3)["tie_turnover"] is None


def test_turnover_complete_rewiring() -> None:
    group = people("a", "b", "c", "d", "e")
    bag = Mailbag()
    for i, sender in enumerate(group):
        bag.send(sender, [group[(i + 1) % 5]], week=WEEK_1)
        bag.send(sender, [group[(i + 2) % 5]], week=WEEK_2)
    assert values(series(bag, group, toy_config()), WEEK_2)["tie_turnover"] == 1.0


# ---- variants ------------------------------------------------------------------------------


def test_cap_variant_drops_large_messages() -> None:
    group = people("a", "b", "c", "d", "e")
    bag = Mailbag()
    complete_graph(bag, group)
    bag.send(group[0], group[1:], n_recipients=25)
    default = values(series(bag, group, toy_config()))
    capped = values(series(bag, group, toy_config(), variant="cap=20"))
    assert default["volume"] == 21
    assert capped["volume"] == 20


def test_exclude_pids_removes_a_person() -> None:
    group = people("a", "b", "c", "d", "e", "f")
    bag = Mailbag()
    complete_graph(bag, group)
    got = values(series(bag, group, toy_config(), exclude=frozenset({group[0].pid})))
    assert got["active_persons"] == 5
    assert got["volume"] == 20


def test_month_variant() -> None:
    group = people("a", "b", "c", "d", "e")
    bag = Mailbag()
    complete_graph(bag, group, WEEK_1)
    complete_graph(bag, group, WEEK_2)
    result = series(bag, group, toy_config(weeks=2), variant="window=month")
    months = {key[2] for key in result}
    assert months == {date(2000, 3, 1)}
    assert result[("observed", "volume", date(2000, 3, 1))] == (40.0, 5)


def test_unknown_variant_is_a_usage_error() -> None:
    a, b = people("a", "b")
    with pytest.raises(UsageError):
        compute_series(
            Mailbag().events(), entities([a, b]), communities({a: 0}), toy_config(), "dedupe"
        )


# ---- communities ---------------------------------------------------------------------------


def test_baseline_communities_split_two_cliques() -> None:
    left = people("a", "b", "c", "d")
    right = people("e", "f", "g", "h")
    late = Person("late")
    bag = Mailbag()
    complete_graph(bag, left)
    complete_graph(bag, right)
    bag.send(left[0], [right[0]])
    comms = baseline_communities(bag.events(), entities([*left, *right, late]), toy_config())
    labels = dict(comms.iter_rows())
    assert len({labels[p.pid] for p in left}) == 1
    assert len({labels[p.pid] for p in right}) == 1
    assert labels[left[0].pid] != labels[right[0].pid]
    assert labels[late.pid] == -1
    schemas.validate(schemas.conform(comms, "communities"), "communities")


def test_baseline_communities_ignore_events_outside_baseline() -> None:
    group = people("a", "b", "c")
    bag = Mailbag()
    complete_graph(bag, group, WEEK_2)
    config = toy_config(weeks=1)
    comms = baseline_communities(bag.events(), entities(group), config)
    assert set(comms.get_column("community").to_list()) == {-1}


def test_frame_is_long_and_sorted() -> None:
    group = people("a", "b", "c", "d", "e")
    bag = Mailbag()
    complete_graph(bag, group)
    out = compute_series(
        bag.events(), entities(group), communities({p: 0 for p in group}), toy_config()
    )
    assert out.columns == [c.name for c in schemas.table("metric_series").cols]
    assert out.height == len(v.SCOPES) * len(v.METRICS) * 2
    assert out.filter(pl.col("week") == WEEK_2).get_column("value").null_count() == 16
