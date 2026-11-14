"""Typed accessors for the counts side outputs (release/tables.py)."""

from __future__ import annotations

from typing import Any

import polars as pl
import pytest

from enron_case.contracts import vocab
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
        "retention_median": 0.1,
        "retention_ci_low": -0.1,
        "retention_ci_high": 0.3,
        "retention_passes": False,
    }
    out = tables.exploratory(pl.DataFrame([row]), k).row(0, named=True)
    for column in (
        "custodians",
        "median_change",
        "p_holm",
        "outcome",
        "loo_stable",
        "equalised_median",
        "retention_median",
        "retention_passes",
        "placebo_custodians",
        "placebo_passes",
    ):
        assert out[column] is None, column
    assert out["hypothesis"] == "H5"


def _funnel_counts() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    ingest: dict[str, Any] = {
        "files_seen": 100,
        "files_parsed": 97,
        "rejected": {"outside_maildir": 1, "no_header_end": 2},
    }
    clean: dict[str, Any] = {
        "records_in": 97,
        "messages_out": 50,
        "removed_exact": 40,
        "removed_subset": 7,
        "flags": {"mass_mailing": 3, "bad_address": 1},
        "dedupe_precision": None,
        "dedupe_recall": None,
    }
    identity: dict[str, Any] = {"addresses": 30, "entities": 25, "precision": None, "recall": None}
    pseudo: dict[str, Any] = {"events": 120, "events_in_network": 110}
    return ingest, clean, identity, pseudo


def test_data_quality_publishes_the_whole_funnel() -> None:
    """Hand-computed: the three main steps first, then rejected files by reason, the dedupe
    split, the five message flags (zero when absent) and events in and out of the network."""
    ingest, clean, identity, pseudo = _funnel_counts()
    out = tables.data_quality(ingest, clean, identity, pseudo)
    got = out.select("order", "step", "count_in", "count_out", "removed").rows()
    assert got == [
        (1, "files parsed", 100, 97, 3),
        (2, "deduplicate", 97, 50, 47),
        (3, "resolve identities", 30, 25, 5),
        (4, "rejected files: no header end", 100, 98, 2),
        (5, "rejected files: outside maildir", 100, 99, 1),
        (6, "deduplicate: exact copies", 97, 57, 40),
        (7, "deduplicate: subset copies", 57, 50, 7),
        (8, "flag: bad address", 50, 49, 1),
        (9, "flag: date out of range", 50, 50, 0),
        (10, "flag: mass mailing", 50, 47, 3),
        (11, "flag: no recipients", 50, 50, 0),
        (12, "flag: self-only", 50, 50, 0),
        (13, "events in the network", 120, 110, 10),
    ]


def test_data_quality_rejects_counts_that_do_not_reconcile() -> None:
    ingest, clean, identity, pseudo = _funnel_counts()
    with pytest.raises(ContractViolation):
        tables.data_quality(ingest, {**clean, "removed_subset": 6}, identity, pseudo)
    with pytest.raises(ContractViolation):
        tables.data_quality({**ingest, "rejected": {"no_header_end": 2}}, clean, identity, pseudo)
    with pytest.raises(ContractViolation):
        tables.data_quality(ingest, {**clean, "flags": {"unknown_flag": 1}}, identity, pseudo)


def test_flag_names_cover_every_message_flag() -> None:
    assert set(tables.FLAG_NAMES) == set(vocab.MESSAGE_FLAGS)
