"""Typed accessors for the counts side outputs (release/tables.py)."""

from __future__ import annotations

from typing import Any

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
