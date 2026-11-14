"""Release tables built from the counts side outputs and the finding and risk results.

Counts only: header field names and rulings come from `ingest_counts`, so this package never
imports ingest code.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from enron_case.contracts import schemas, vocab
from enron_case.errors import ContractViolation

STEP_PARSE = "files parsed"
STEP_DEDUPE = "deduplicate"
STEP_IDENTITY = "resolve identities"
RULE_DEDUPE = "exact+subset"
RULE_IDENTITY = "N1-N4"
STEP_MANUAL = "manual merge check"
RULE_MANUAL = "seeded sample, judged by a person"


def require(counts: dict[str, Any], file: str, key: str) -> object:
    """A counts value, or a ContractViolation naming the missing file or key."""
    if key not in counts:
        raise ContractViolation(f"counts '{file}' lack '{key}'")
    value: object = counts[key]
    return value


def require_int(counts: dict[str, Any], file: str, key: str) -> int:
    value = require(counts, file, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"counts '{file}': '{key}' is not an integer")
    return value


def require_rate(counts: dict[str, Any], file: str, key: str) -> float | None:
    """A precision or recall: a number, or null where there is no ground truth."""
    value = require(counts, file, key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContractViolation(f"counts '{file}': '{key}' is not a number")
    return float(value)


def _count(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"ingest_counts: occurrences of '{field}' is not an integer")
    return value


def _ruling(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation(f"ingest_counts: ruling of '{field}' is not a string")
    return value


def require_mapping(counts: dict[str, Any], file: str, key: str) -> dict[str, object]:
    value = require(counts, file, key)
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ContractViolation(f"counts '{file}': '{key}' is not a mapping")
    return value


def data_quality(
    ingest: dict[str, Any],
    clean: dict[str, Any],
    identity: dict[str, Any],
    manual: dict[str, Any] | None = None,
) -> pl.DataFrame:
    """One row per pipeline step: what went in, what came out, the rule and its measured
    precision and recall where ground truth exists."""
    files_seen = require_int(ingest, "ingest_counts", "files_seen")
    files_parsed = require_int(ingest, "ingest_counts", "files_parsed")
    records = require_int(clean, "clean_counts", "records_in")
    messages = require_int(clean, "clean_counts", "messages_out")
    addresses = require_int(identity, "identity_counts", "addresses")
    entities = require_int(identity, "identity_counts", "entities")
    rows = [
        (1, STEP_PARSE, files_seen, files_parsed, None, None, None),
        (
            2,
            STEP_DEDUPE,
            records,
            messages,
            RULE_DEDUPE,
            require_rate(clean, "clean_counts", "dedupe_precision"),
            require_rate(clean, "clean_counts", "dedupe_recall"),
        ),
        (
            3,
            STEP_IDENTITY,
            addresses,
            entities,
            RULE_IDENTITY,
            require_rate(identity, "identity_counts", "precision"),
            require_rate(identity, "identity_counts", "recall"),
        ),
    ]
    checked = (manual or {}).get("manual_checked")
    if checked:
        correct = int((manual or {})["manual_correct"])
        rows.append(
            (4, STEP_MANUAL, int(checked), correct, RULE_MANUAL, correct / int(checked), None)
        )
    return pl.DataFrame(
        [
            {
                "order": order,
                "step": step,
                "count_in": count_in,
                "count_out": count_out,
                "removed": count_in - count_out,
                "rule": rule,
                "precision": precision,
                "recall": recall,
            }
            for order, step, count_in, count_out, rule, precision, recall in rows
        ],
        schema=schemas.table("data_quality").polars_schema,
    )


def header_fields(ingest: dict[str, Any]) -> pl.DataFrame:
    """Every header field name seen, how often, and the ruling the parser applied to it."""
    occurrences = {
        name: _count(n, name)
        for name, n in require_mapping(ingest, "ingest_counts", "header_fields").items()
    }
    rulings = {
        name: _ruling(r, name)
        for name, r in require_mapping(ingest, "ingest_counts", "header_rulings").items()
    }
    unruled = sorted(set(occurrences) - set(rulings))
    if unruled:
        raise ContractViolation(f"ingest_counts: {len(unruled)} header fields without a ruling")
    known = {name: n for name, n in occurrences.items() if name in vocab.KNOWN_HEADER_FIELDS}
    other = sum(n for name, n in occurrences.items() if name not in vocab.KNOWN_HEADER_FIELDS)
    names = list(known)
    counts = list(known.values())
    labels = [rulings[name] for name in known]
    if other:
        # Unknown names are never published: they can be fragments of message text.
        names.append(vocab.OTHER_HEADER_FIELD)
        counts.append(other)
        labels.append("dropped")
    return pl.DataFrame(
        {"field": names, "occurrences": counts, "ruling": labels},
        schema=schemas.table("header_fields").polars_schema,
    )


def artifact_checks(results: pl.DataFrame, k_min: int) -> pl.DataFrame:
    """The artifact checks; a count of custodians below k is suppressed."""
    return results.with_columns(
        pl.when((pl.col("check") == "within_custodian") & (pl.col("n_units") < k_min))
        .then(None)
        .otherwise(pl.col("n_units"))
        .alias("n_units")
    )


def exploratory(results: pl.DataFrame, k_min: int) -> pl.DataFrame:
    """E1–E20 results. A comparison over fewer than k custodians is suppressed with its
    statistics (the count and every number derived from it)."""
    crisis = (
        "custodians",
        "median_change",
        "ci_low",
        "ci_high",
        "p",
        "p_holm",
        "equalised_median",
        "equalised_ci_low",
        "equalised_ci_high",
        "equalised_p",
    )
    placebo = ("placebo_custodians", "placebo_median", "placebo_ci_low", "placebo_ci_high")
    small_crisis = pl.col("custodians") < k_min
    small_placebo = pl.col("placebo_custodians") < k_min
    return results.with_columns(
        *[pl.when(small_crisis).then(None).otherwise(pl.col(c)).alias(c) for c in crisis],
        *[pl.when(small_placebo).then(None).otherwise(pl.col(c)).alias(c) for c in placebo],
    )
