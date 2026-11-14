"""T063: uniqueness and anonymity-set sizes on toy tables with known answers."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from enron_case.errors import PipelineError
from enron_case.risk.features import node_features, weekly_activity
from enron_case.risk.uniqueness import (
    aggregate_set_sizes,
    anonymity_set_sizes,
    cell_set_sizes,
    summarize,
)

W1, W2 = date(2001, 1, 1), date(2001, 1, 8)


def test_set_sizes_count_identical_feature_rows() -> None:
    features = pl.DataFrame(
        {"node": ["a", "b", "c", "d", "e"], "degree": [1, 1, 2, 2, 3], "first": [1, 1, 1, 2, 1]}
    )
    # (1,1) twice; (2,1), (2,2), (3,1) once each.
    assert anonymity_set_sizes(features, "node") == [2, 2, 1, 1, 1]


def test_summary_of_known_sets() -> None:
    result = summarize([2, 2, 1, 1, 1])
    assert result.unique_share == pytest.approx(3 / 5)
    assert result.median_anonymity_set == 1.0
    assert summarize([5, 5, 5, 5, 5, 12]).median_anonymity_set == 5.0


def test_summary_refuses_empty_population() -> None:
    with pytest.raises(PipelineError):
        summarize([])


def test_cells_give_each_member_the_cell_size() -> None:
    assert cell_set_sizes([3, None, 0, 1]) == [3, 3, 3, 1]
    assert cell_set_sizes([2.4]) == [2, 2]  # noisy counts are rounded


def test_aggregate_release_reads_person_count_columns_only() -> None:
    tables = {
        "degree_distribution": pl.DataFrame({"persons": [5, None, 6]}),
        "community_groups": pl.DataFrame({"n_persons": [7]}),
        "community_graph": pl.DataFrame({"n_messages": [900]}),
    }
    sizes = aggregate_set_sizes(tables)
    assert sorted(sizes) == [5] * 5 + [6] * 6 + [7] * 7
    assert summarize(sizes).unique_share == 0.0


def test_node_features_on_hand_built_graph() -> None:
    edges = pl.DataFrame(
        {
            "week": [W1, W1, W2, W2, W2],
            "src": ["a", "a", "b", "c", "c"],
            "dst": ["b", "c", "a", "a", "c"],  # c -> c is a self-loop and is ignored
        }
    )
    activity = weekly_activity(edges)
    a_rows = activity.filter(pl.col("node") == "a").select("week", "n_out", "n_in").rows()
    assert a_rows == [(W1, 2, 0), (W2, 0, 2)]
    features = node_features(edges)
    assert features.get_column("node").to_list() == ["a", "b", "c"]
    assert features.get_column("degree").to_list() == [2, 1, 1]
    assert features.get_column("first_week").to_list() == [W1, W1, W1]
    assert features.get_column("last_week").to_list() == [W2, W2, W2]
    # b and c: same degree, same weeks, same per-week counts -> one set of two.
    assert anonymity_set_sizes(features, "node") == [1, 2, 2]
