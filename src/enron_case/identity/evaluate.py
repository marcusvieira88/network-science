"""Identity evaluation (T036): pairwise precision/recall and the manual-review sampler.

Pairwise scores treat "same entity" as a relation on address pairs. Only addresses present in
both the prediction and the ground truth are scored. A score is None when its denominator is
zero (no predicted pairs, or no true pairs).

The sampler draws merges for a manual review that happens inside the ingest zone (T046). Only
the counts (`manual_counts`) leave it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from math import comb

import polars as pl


def pairwise_scores(
    entity_of: Mapping[str, str], truth_of: Mapping[str, str]
) -> tuple[float | None, float | None]:
    """(precision, recall) of predicted same-entity pairs against true same-entity pairs."""
    scored = sorted(set(entity_of) & set(truth_of))
    predicted = _pairs(Counter(entity_of[a] for a in scored))
    actual = _pairs(Counter(truth_of[a] for a in scored))
    correct = _pairs(Counter((entity_of[a], truth_of[a]) for a in scored))
    precision = correct / predicted if predicted else None
    recall = correct / actual if actual else None
    return precision, recall


def _pairs(cluster_sizes: Counter[object]) -> int:
    return sum(comb(n, 2) for n in cluster_sizes.values())


def sample_merges(address_map: pl.DataFrame, n: int, seed: int) -> pl.DataFrame:
    """Up to `n` merged rows (rule not null), drawn with a fixed seed, sorted by address."""
    merges = address_map.drop_nulls("rule").sort("addr")
    if merges.height <= n:
        return merges
    return merges.sample(n=n, seed=seed).sort("addr")


def manual_counts(verdicts: Sequence[bool]) -> tuple[int, int]:
    """(checked, correct) from reviewer verdicts; the verdicts themselves are not kept."""
    return len(verdicts), sum(verdicts)
