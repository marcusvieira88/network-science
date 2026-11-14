"""Typed accessors for the counts side outputs (release/tables.py)."""

from __future__ import annotations

from typing import Any

import polars as pl
import pytest

from enron_case.errors import ContractViolation
from enron_case.release import tables


def test_typed_count_accessors_fail_loudly() -> None:
    counts: dict[str, Any] = {"n": True, "rate": "high", "map": [1], "ok": 3, "none": None}
    with pytest.raises(ContractViolation):
        tables.require_int(counts, "c", "n")  # a bool is not a count
    with pytest.raises(ContractViolation):
        tables.require_rate(counts, "c", "rate")
    with pytest.raises(ContractViolation):
        tables.require_mapping(counts, "c", "map")
    with pytest.raises(ContractViolation):
        tables.require_int(counts, "c", "missing")
    assert tables.require_int(counts, "c", "ok") == 3
    assert tables.require_rate(counts, "c", "none") is None


def test_header_fields_reject_malformed_counts() -> None:
    bad_count = {"header_fields": {"From": "many"}, "header_rulings": {"From": "identifier"}}
    with pytest.raises(ContractViolation):
        tables.header_fields(bad_count)
    bad_ruling = {"header_fields": {"From": 3}, "header_rulings": {"From": 1}}
    with pytest.raises(ContractViolation):
        tables.header_fields(bad_ruling)


def test_exploratory_rows_below_k_hide_every_derived_value() -> None:
    k = 5
    row: dict[str, object] = {
        "order": 1,
        "hypothesis": "H5",
        "family": "first",
        "measure": "m",
        "direction": "up",
        "custodians": 3,
        "median_change": 0.2,
        "ci_low": 0.1,
        "ci_high": 0.3,
        "p": 0.01,
        "p_holm": 0.02,
        "placebo_custodians": 4,
        "placebo_median": 0.0,
        "placebo_ci_low": -0.1,
        "placebo_ci_high": 0.1,
        "placebo_passes": True,
        "loo_stable": True,
        "outcome": "confident",
        "caveat": "",
        "equalised_median": 0.1,
        "equalised_ci_low": 0.05,
        "equalised_ci_high": 0.2,
        "equalised_p": 0.01,
    }
    out = tables.exploratory(pl.DataFrame([row]), k).row(0, named=True)
    for column in (
        "custodians",
        "median_change",
        "p_holm",
        "outcome",
        "loo_stable",
        "equalised_median",
        "placebo_custodians",
        "placebo_passes",
    ):
        assert out[column] is None, column
    assert out["hypothesis"] == "H5"
