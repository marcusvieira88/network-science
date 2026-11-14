"""Identity evaluation (T036): the manual-review sampler and its counts. Pairwise scores
against the ground truth come from `clean.pairs`.

The sampler draws merges for a manual review that happens inside the ingest zone (T046). Only
the counts (`manual_counts`) leave it.
"""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl


def sample_merges(address_map: pl.DataFrame, n: int, seed: int) -> pl.DataFrame:
    """Up to `n` merged rows (rule not null), drawn with a fixed seed, sorted by address."""
    merges = address_map.drop_nulls("rule").sort("addr")
    if merges.height <= n:
        return merges
    return merges.sample(n=n, seed=seed).sort("addr")


def manual_counts(verdicts: Sequence[bool]) -> tuple[int, int]:
    """(checked, correct) from reviewer verdicts; the verdicts themselves are not kept."""
    return len(verdicts), sum(verdicts)


def manual_counts_by_rule(
    rules: Sequence[str], verdicts: Sequence[bool | None]
) -> dict[str, dict[str, int]]:
    """Rule -> {checked, correct} over the judged merges (None: skipped, not counted). Counts
    only, never which address was judged."""
    out: dict[str, dict[str, int]] = {}
    for rule, verdict in zip(rules, verdicts, strict=True):
        if verdict is None:
            continue
        counts = out.setdefault(rule, {"checked": 0, "correct": 0})
        counts["checked"] += 1
        counts["correct"] += int(verdict)
    return dict(sorted(out.items()))
