"""Typed accessors for the counts side outputs (release/tables.py)."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from enron_case.config import Config
from enron_case.context import StageContext
from enron_case.contracts import vocab
from enron_case.contracts.counts import JsonObject
from enron_case.errors import ContractViolation, PrivacyViolation
from enron_case.release import tables
from enron_case.zones import Paths, Zone


def test_typed_count_accessors_fail_loudly() -> None:
    counts: JsonObject = {"n": True, "rate": "high", "map": [1], "ok": 3, "none": None}
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
    bad_count: JsonObject = {
        "header_fields": {"From": "many"},
        "header_rulings": {"From": "identifier"},
    }
    with pytest.raises(ContractViolation):
        tables.header_fields(bad_count)
    bad_ruling: JsonObject = {"header_fields": {"From": 3}, "header_rulings": {"From": 1}}
    with pytest.raises(ContractViolation):
        tables.header_fields(bad_ruling)


def test_header_field_without_a_ruling_fails() -> None:
    unruled: JsonObject = {
        "header_fields": {"From": 3, "Date": 2},
        "header_rulings": {"From": "identifier"},
    }
    with pytest.raises(ContractViolation, match="1 header fields without a ruling"):
        tables.header_fields(unruled)


def test_unknown_header_names_collapse_into_one_dropped_row() -> None:
    """Hand-computed: the two unknown names (4 + 1 occurrences) become one "(other)" row of 5,
    labelled dropped whatever ruling the parser stored; neither spelling is published."""
    unknown_a = "X-Unlisted-Fragment"
    unknown_b = "Looks Like Body Text"
    counts: JsonObject = {
        "header_fields": {"From": 3, unknown_a: 4, unknown_b: 1},
        "header_rulings": {"From": "identifier", unknown_a: "content", unknown_b: "content"},
    }
    out = tables.header_fields(counts)
    assert out.rows() == [("From", 3, "identifier"), (vocab.OTHER_HEADER_FIELD, 5, "dropped")]
    published = " ".join(str(value) for row in out.rows() for value in row)
    assert unknown_a not in published
    assert unknown_b not in published


def test_only_known_header_names_publish_no_other_row() -> None:
    counts: JsonObject = {
        "header_fields": {"Date": 2},
        "header_rulings": {"Date": "usable"},
    }
    assert tables.header_fields(counts).rows() == [("Date", 2, "usable")]


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
        "equalised_p_holm": 0.2,
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
        "equalised_p_holm",
        "retention_median",
        "retention_passes",
        "placebo_custodians",
        "placebo_passes",
    ):
        assert out[column] is None, column
    assert out["hypothesis"] == "H5"


CI = 0.95


def _funnel_counts() -> tuple[JsonObject, JsonObject, JsonObject, JsonObject]:
    ingest: JsonObject = {
        "files_seen": 100,
        "files_parsed": 97,
        "rejected": {"outside_maildir": 1, "no_header_end": 2},
    }
    clean: JsonObject = {
        "records_in": 97,
        "messages_out": 50,
        "removed_exact": 40,
        "removed_subset": 7,
        "flags": {"mass_mailing": 3, "bad_address": 1},
        "dedupe_precision": None,
        "dedupe_recall": None,
    }
    identity: JsonObject = {"addresses": 30, "entities": 25, "precision": None, "recall": None}
    pseudo: JsonObject = {"events": 120, "events_in_network": 110, "messages_without_time": 2}
    return ingest, clean, identity, pseudo


def test_data_quality_publishes_the_whole_funnel() -> None:
    """Hand-computed: the three main steps first, then rejected files by reason, the dedupe
    split, the five message flags (zero when absent) and events in and out of the network."""
    ingest, clean, identity, pseudo = _funnel_counts()
    out = tables.data_quality(ingest, clean, identity, pseudo, CI)
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
        (13, "messages without a timestamp", 50, 48, 2),
        (14, "events in the network", 120, 110, 10),
    ]


def test_data_quality_rejects_counts_that_do_not_reconcile() -> None:
    ingest, clean, identity, pseudo = _funnel_counts()
    with pytest.raises(ContractViolation):
        tables.data_quality(ingest, {**clean, "removed_subset": 6}, identity, pseudo, CI)
    with pytest.raises(ContractViolation):
        tables.data_quality(
            {**ingest, "rejected": {"no_header_end": 2}}, clean, identity, pseudo, CI
        )
    with pytest.raises(ContractViolation):
        tables.data_quality(ingest, {**clean, "flags": {"unknown_flag": 1}}, identity, pseudo, CI)


def test_flag_names_cover_every_message_flag() -> None:
    assert set(tables.FLAG_NAMES) == set(vocab.MESSAGE_FLAGS)


def test_clopper_pearson_known_answers() -> None:
    # All 50 correct: the lower bound is 0.025 ** (1 / 50); the upper bound is 1.
    low, high = tables.clopper_pearson(50, 50, CI)
    assert low == pytest.approx(0.025 ** (1 / 50), abs=1e-9)
    assert high == 1.0
    # 5 of 10 (tabulated exact binomial interval): 0.187086 to 0.812914.
    low, high = tables.clopper_pearson(5, 10, CI)
    assert low == pytest.approx(0.187086, abs=1e-6)
    assert high == pytest.approx(0.812914, abs=1e-6)
    assert tables.clopper_pearson(0, 4, CI)[0] == 0.0


def test_manual_check_rows_carry_an_interval_and_the_rule_composition() -> None:
    ingest, clean, identity, pseudo = _funnel_counts()
    manual = {
        "manual_checked": 50,
        "manual_correct": 48,
        "manual_by_rule": {
            "N2": {"checked": 10, "correct": 8},
            "N1": {"checked": 40, "correct": 40},
        },
    }
    out = tables.data_quality(ingest, clean, identity, pseudo, CI, manual)
    rows = out.filter(pl.col("step").str.starts_with("manual merge check")).rows(named=True)
    assert [(r["order"], r["step"], r["count_in"], r["count_out"]) for r in rows] == [
        (4, "manual merge check", 50, 48),
        (5, "manual merge check: rule N1", 40, 40),
        (6, "manual merge check: rule N2", 10, 8),
    ]
    assert rows[0]["precision"] == pytest.approx(0.96)
    # Exact binomial interval for 48 of 50 at 95 %: 0.8629 to 0.9951.
    assert rows[0]["precision_ci_low"] == pytest.approx(0.8629, abs=1e-4)
    assert rows[0]["precision_ci_high"] == pytest.approx(0.9951, abs=1e-4)
    assert rows[1]["precision_ci_low"] == pytest.approx(0.025 ** (1 / 40), abs=1e-9)
    assert out.filter(pl.col("step") == "resolve identities").item(0, "precision_ci_low") is None
    assert out.get_column("order").to_list() == list(range(1, out.height + 1))


def test_manual_rule_composition_must_add_up() -> None:
    ingest, clean, identity, pseudo = _funnel_counts()
    manual = {
        "manual_checked": 50,
        "manual_correct": 48,
        "manual_by_rule": {"N1": {"checked": 40, "correct": 40}},
    }
    with pytest.raises(ContractViolation):
        tables.data_quality(ingest, clean, identity, pseudo, CI, manual)


def test_manual_check_without_a_rule_split_publishes_one_row() -> None:
    """A review stored before per-rule counts were kept: only the total row, no rule rows."""
    ingest, clean, identity, pseudo = _funnel_counts()
    manual: JsonObject = {"manual_checked": 20, "manual_correct": 19}
    out = tables.data_quality(ingest, clean, identity, pseudo, CI, manual)
    rows = out.filter(pl.col("step").str.starts_with("manual merge check"))
    assert rows.select("step", "count_in", "count_out").rows() == [("manual merge check", 20, 19)]


def test_manual_rule_counts_that_are_not_a_mapping_fail() -> None:
    ingest, clean, identity, pseudo = _funnel_counts()
    manual: JsonObject = {
        "manual_checked": 10,
        "manual_correct": 9,
        "manual_by_rule": {"N1": [10, 9]},
    }
    with pytest.raises(ContractViolation, match="counts of rule 'N1' are not a mapping"):
        tables.data_quality(ingest, clean, identity, pseudo, CI, manual)


def test_within_custodian_check_below_k_hides_its_statistics() -> None:
    # A within-custodian change over 3 custodians describes fewer than k=5 persons: the count
    # and everything computed from those custodians go; the note is fixed text and stays.
    results = pl.DataFrame(
        {
            "hypothesis": ["H2", "H3"],
            "check": ["baseline_placebo", "within_custodian"],
            "statistic": [1.5, -0.2],
            "ci_low": [1.0, -0.4],
            "ci_high": [2.0, 0.1],
            "n_units": [3, 3],
            "passes": [False, True],
            "note": ["drift", "no change"],
        }
    )
    out = tables.artifact_checks(results, 5)
    placebo, within = out.row(0, named=True), out.row(1, named=True)
    # The placebo counts weeks, not persons: untouched.
    assert (placebo["statistic"], placebo["n_units"], placebo["passes"]) == (1.5, 3, False)
    assert [within[c] for c in ("statistic", "ci_low", "ci_high", "n_units", "passes")] == [
        None
    ] * 5
    assert within["note"] == "no change"


def test_committed_manual_check_is_used_when_the_run_has_none(tmp_path: Path) -> None:
    """A fresh clone has no counts zone from the person's review: the committed copy in the
    checks zone is published instead. Sample runs never use it."""
    paths = Paths(tmp_path / "data", tmp_path / "release", tmp_path / "ui", tmp_path / "docs")
    checks = paths.dir(Zone.CHECKS)
    checks.mkdir(parents=True)
    (checks / "identity_manual.json").write_text('{"manual_checked": 50, "manual_correct": 49}')
    real = StageContext("release", Config(), paths, False, lambda _m: None)
    assert real.read_optional_counts("identity_manual") == {
        "manual_checked": 50,
        "manual_correct": 49,
    }
    sample = StageContext("release", Config(), paths, True, lambda _m: None)
    assert sample.read_optional_counts("identity_manual") is None


def test_review_writes_the_committed_copy(tmp_path: Path) -> None:
    paths = Paths(tmp_path / "data", tmp_path / "release", tmp_path / "ui", tmp_path / "docs")
    ctx = StageContext("identity", Config(), paths, False, lambda _m: None)
    ctx.write_check("identity_manual", {"manual_checked": 2, "manual_correct": 2})
    with pytest.raises(PrivacyViolation):
        ctx.write_check("identity_manual", {"note": "someone@example.com"})
