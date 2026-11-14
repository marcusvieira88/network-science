"""Pairwise precision and recall against hand-computed cases."""

from __future__ import annotations

from enron_case.clean.pairs import pairwise_scores


def test_pairwise_scores_on_hand_computed_case() -> None:
    truth = {"a": "T1", "b": "T1", "c": "T1", "d": "T2"}
    predicted = {"a": "a", "b": "a", "c": "c", "d": "a"}
    # predicted pairs ab, ad, bd; true pairs ab, ac, bc; correct ab only
    assert pairwise_scores(predicted, truth) == (1 / 3, 1 / 3)
    assert pairwise_scores({"a": "a", "d": "d"}, truth) == (None, None)


def test_pairwise_scores_ignore_addresses_without_truth() -> None:
    truth = {"a": "T1", "b": "T1"}
    assert pairwise_scores({"a": "a", "b": "a", "z": "a"}, truth) == (1.0, 1.0)
