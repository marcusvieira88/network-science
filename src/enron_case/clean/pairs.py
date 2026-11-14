"""Pairwise precision and recall of a clustering against ground truth.

"Same cluster" is treated as a relation on item pairs. Shared by the deduplication score (files
of one message) and the identity score (addresses of one entity). Only items present in both
the prediction and the truth are scored. A score is None when its denominator is zero (no
predicted pairs, or no true pairs).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from math import comb


def pairwise_scores(
    predicted: Mapping[str, str], truth: Mapping[str, str]
) -> tuple[float | None, float | None]:
    """(precision, recall) of predicted same-cluster pairs against true same-cluster pairs."""
    scored = sorted(set(predicted) & set(truth))
    predicted_pairs = _pairs(Counter(predicted[item] for item in scored))
    true_pairs = _pairs(Counter(truth[item] for item in scored))
    agreed = _pairs(Counter((predicted[item], truth[item]) for item in scored))
    precision = agreed / predicted_pairs if predicted_pairs else None
    recall = agreed / true_pairs if true_pairs else None
    return precision, recall


def _pairs(cluster_sizes: Counter[object]) -> int:
    return sum(comb(n, 2) for n in cluster_sizes.values())
