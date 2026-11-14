"""T070: kanon.py is the single enforcement point for minimum group size and identifiers."""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest
from hypothesis import given
from hypothesis import strategies as st

from enron_case.errors import PrivacyViolation
from enron_case.release import kanon
from enron_case.synth import SynthOutput

K = 5
PID = "p_abcdefghijklmnop"
ORG_PID = "o_abcdefghijklmnop"


def test_privacy_violation_exits_6() -> None:
    assert PrivacyViolation.exit_code == 6


def test_counts_below_k_are_suppressed_with_their_dependents() -> None:
    df = pl.DataFrame({"n": [0, 4, 5, 9], "value": [1.0, 2.0, 3.0, 4.0]})
    out = kanon.suppress_below(df, "n", K, dependents=("value",))
    assert out["n"].to_list() == [None, None, 5, 9]
    assert out["value"].to_list() == [None, None, 3.0, 4.0]


def test_rows_below_k_are_dropped() -> None:
    df = pl.DataFrame({"group": ["a", "b", "c"], "senders": [4, 5, 1]})
    assert kanon.drop_below(df, "senders", K)["group"].to_list() == ["b"]


def test_single_suppressed_cell_gets_a_complement() -> None:
    # Period P: buckets 6, 18, 14, 3. With the period total known to an attacker, the lone
    # suppressed 3 would be total - (6+18+14); the smallest published cell is suppressed too.
    df = pl.DataFrame(
        {
            "period": ["P"] * 4 + ["Q"] * 4,
            "bucket": ["1", "2-4", "5-9", "10+"] * 2,
            "persons": [6, 18, 14, 3, 7, 8, 9, 10],
        }
    )
    out = kanon.suppress_partition(df, "persons", "period", K)
    assert out["persons"].to_list() == [None, 18, 14, None, 7, 8, 9, 10]


def test_a_true_zero_does_not_protect_a_lone_small_cell() -> None:
    # Period P: 0, 3, 18, 14. Both 0 and 3 are below k, but total - (18 + 14) = 3 + 0 still
    # reveals the 3: a zero cell is no second suppression, so the smallest published cell goes.
    df = pl.DataFrame({"period": ["P"] * 4, "persons": [0, 3, 18, 14]})
    out = kanon.suppress_partition(df, "persons", "period", K)
    assert out["persons"].to_list() == [None, None, 18, None]


def test_already_suppressed_cells_count_as_hidden() -> None:
    # R2 re-suppresses a table whose small cells are already null: one null plus a new small
    # cell are two hidden cells and need no complement.
    df = pl.DataFrame({"period": ["P"] * 3, "persons": pl.Series([None, 2, 9], dtype=pl.Int64)})
    assert kanon.suppress_partition(df, "persons", "period", K)["persons"].to_list() == [
        None,
        None,
        9,
    ]


def test_two_suppressed_cells_need_no_complement() -> None:
    df = pl.DataFrame({"period": ["P"] * 3, "persons": [1, 2, 9]})
    out = kanon.suppress_partition(df, "persons", "period", K)
    assert out["persons"].to_list() == [None, None, 9]


@pytest.mark.parametrize("bad", [PID, ORG_PID, "someone@example.com", f"x {PID} y"])
def test_identifiers_are_refused(bad: str) -> None:
    df = pl.DataFrame({"group": ["G01", bad], "n_persons": [5, 6]})
    with pytest.raises(PrivacyViolation):
        kanon.check("community_groups", df, K)


def test_person_count_below_k_is_refused() -> None:
    df = pl.DataFrame({"group": ["G01", "G02"], "n_persons": [5, 4]})
    with pytest.raises(PrivacyViolation):
        kanon.check("community_groups", df, K)


def test_metric_value_without_its_group_is_refused() -> None:
    df = pl.DataFrame(
        {"metric": ["density"], "value": [0.1], "n_active": pl.Series([None], dtype=pl.Int64)}
    )
    with pytest.raises(PrivacyViolation):
        kanon.check("weekly_metrics", df, K)


def test_active_persons_value_below_k_is_refused() -> None:
    df = pl.DataFrame({"metric": ["active_persons"], "value": [3.0], "n_active": [9]})
    with pytest.raises(PrivacyViolation):
        kanon.check("weekly_metrics", df, K)


def test_lone_suppressed_cell_is_refused() -> None:
    df = pl.DataFrame(
        {"period": ["P", "P"], "persons": pl.Series([None, 9], dtype=pl.Int64)},
    )
    with pytest.raises(PrivacyViolation):
        kanon.check("degree_distribution", df, K)


def test_compliant_table_passes() -> None:
    df = pl.DataFrame({"group": ["G01", "other"], "n_persons": [5, 12]})
    kanon.check("community_groups", df, K)


counts = st.lists(st.integers(min_value=0, max_value=40), min_size=1, max_size=30)


@given(values=counts)
def test_property_no_count_below_k_leaves_suppress(values: list[int]) -> None:
    df = pl.DataFrame({"persons": values, "value": [float(v) for v in values]})
    out = kanon.suppress_below(df, "persons", K, dependents=("value",))
    published = out["persons"].drop_nulls()
    assert (published >= K).all()
    assert out.filter(pl.col("persons").is_null())["value"].null_count() == out.height - len(
        published
    )


@given(
    periods=st.lists(
        st.lists(st.integers(min_value=0, max_value=30), min_size=1, max_size=6),
        min_size=1,
        max_size=5,
    )
)
def test_property_degree_tables_pass_check_after_enforcement(periods: list[list[int]]) -> None:
    rows = [
        {"period": f"P{i}", "degree_bucket": str(j), "persons": n}
        for i, cells in enumerate(periods)
        for j, n in enumerate(cells)
    ]
    df = pl.DataFrame(rows)
    out = kanon.suppress_partition(df, "persons", "period", K)
    kanon.check("degree_distribution", out, K)
    assert (out["persons"].drop_nulls() >= K).all()
    hidden = df.with_columns(out["persons"].is_null().alias("hidden"))
    for _, cells in hidden.group_by("period"):
        hidden_small = cells.filter(pl.col("hidden") & pl.col("persons").is_between(1, K - 1))
        positive_hidden = cells.filter(pl.col("hidden") & (pl.col("persons") > 0)).height
        published = cells.filter(~pl.col("hidden")).height
        # A small count is never the only non-zero hidden value next to published cells.
        assert not (hidden_small.height and positive_hidden == 1 and published > 0)


@given(position=st.integers(min_value=0, max_value=9), token=st.sampled_from([PID, "a@b"]))
def test_property_identifier_anywhere_is_refused(position: int, token: str) -> None:
    labels = [f"G{i:02d}" for i in range(10)]
    labels[position] = token
    df = pl.DataFrame({"group": labels, "n_persons": [K] * 10})
    with pytest.raises(PrivacyViolation):
        kanon.check("community_groups", df, K)


def test_release_fixture_degree_table_passes_check(synth: SynthOutput) -> None:
    kanon.check("degree_distribution", synth.table("degree_distribution"), K)


def _scopes(observed: list[int | None], core: list[int | None]) -> pl.DataFrame:
    """weekly_metrics rows of one metric: week i has the given n_active per scope."""
    weeks = [date(2001, 1, 1) + timedelta(weeks=i) for i in range(len(observed))]
    rows = [
        {
            "scope": scope,
            "week": week,
            "metric": "volume",
            "value": None if n is None else n * 10.0,
            "n_active": n,
            "variant": "default",
        }
        for scope, counts in (("observed", observed), ("core", core))
        for week, n in zip(weeks, counts, strict=True)
    ]
    return pl.DataFrame(rows, schema_overrides={"n_active": pl.Int64})


def test_core_scope_hiding_fewer_than_k_outside_it_is_suppressed() -> None:
    # Week 0: observed 12, core 9, so 3 active persons are outside the core: observed minus core
    # would describe them. Week 1 differs by 0 and week 2 by 5; both stay published.
    df = _scopes([12, 9, 20], [9, 9, 15])
    out = kanon.suppress_nested_scopes(df, K)
    core = out.filter(pl.col("scope") == "core").sort("week")
    assert core["n_active"].to_list() == [None, 9, 15]
    assert core["value"].to_list() == [None, 90.0, 150.0]
    assert out.filter(pl.col("scope") == "observed")["n_active"].to_list() == [12, 9, 20]


def test_check_refuses_a_scope_difference_below_k() -> None:
    with pytest.raises(PrivacyViolation, match="scope"):
        kanon.check("weekly_metrics", _scopes([12], [9]), K)
    kanon.check("weekly_metrics", _scopes([12], [None]), K)
