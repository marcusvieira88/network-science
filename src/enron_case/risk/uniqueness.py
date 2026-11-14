"""How unique persons are on what an attacker can observe in a release.

For a node-level release a person's anonymity set is the number of persons with exactly the same
observable features (degree, weekly activity vector, first and last active week). For an
aggregate release no person-level record exists; a person can at best be placed in a published
cell, so the anonymity set is the size of that cell.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import polars as pl

from enron_case.errors import PipelineError

SET_SIZE = "set_size"
# Release-table columns (contracts/schemas.py) that count persons in a published cell.
PERSON_COUNT_COLUMNS = ("persons", "n_persons")


@dataclass(frozen=True)
class Uniqueness:
    unique_share: float
    median_anonymity_set: float


def anonymity_set_sizes(features: pl.DataFrame, id_col: str) -> list[int]:
    """For each row, how many rows share all feature columns (every column but `id_col`)."""
    keys = [c for c in features.columns if c != id_col]
    if not keys:
        raise PipelineError("uniqueness needs at least one feature column")
    sizes = features.select(pl.len().over(keys).alias(SET_SIZE)).get_column(SET_SIZE)
    return [int(s) for s in sizes.to_list()]


def cell_set_sizes(counts: Iterable[float | int | None]) -> list[int]:
    """Anonymity sets implied by published person counts: a cell of n persons gives each of
    them a set of size n. Suppressed (null) and empty cells hide nobody and are skipped."""
    sizes: list[int] = []
    for count in counts:
        if count is None:
            continue
        n = round(count)
        sizes.extend([n] * n if n > 0 else [])
    return sizes


def aggregate_set_sizes(tables: dict[str, pl.DataFrame]) -> list[int]:
    """Anonymity sets from every person-count column in an aggregate release."""
    sizes: list[int] = []
    for name in sorted(tables):
        for column in PERSON_COUNT_COLUMNS:
            if column in tables[name].columns:
                sizes.extend(cell_set_sizes(tables[name].get_column(column).to_list()))
    return sizes


def summarize(sizes: list[int]) -> Uniqueness:
    """Share of persons alone in their set, and the median set size."""
    if not sizes:
        raise PipelineError("no persons to measure uniqueness on")
    values = np.asarray(sizes, dtype=np.float64)
    return Uniqueness(
        unique_share=float(np.mean(values == 1)),
        median_anonymity_set=float(np.median(values)),
    )
