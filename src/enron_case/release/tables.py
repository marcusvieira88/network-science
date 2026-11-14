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


def require(counts: dict[str, Any], file: str, key: str) -> Any:
    """A counts value, or a ContractViolation naming the missing file or key."""
    if key not in counts:
        raise ContractViolation(f"counts '{file}' lack '{key}'")
    return counts[key]


def data_quality(
    ingest: dict[str, Any],
    clean: dict[str, Any],
    identity: dict[str, Any],
    manual: dict[str, Any] | None = None,
) -> pl.DataFrame:
    """One row per pipeline step: what went in, what came out, the rule and its measured
    precision and recall where ground truth exists."""
    files_seen = require(ingest, "ingest_counts", "files_seen")
    files_parsed = require(ingest, "ingest_counts", "files_parsed")
    records = require(clean, "clean_counts", "records_in")
    messages = require(clean, "clean_counts", "messages_out")
    addresses = require(identity, "identity_counts", "addresses")
    entities = require(identity, "identity_counts", "entities")
    rows = [
        (1, STEP_PARSE, files_seen, files_parsed, None, None, None),
        (
            2,
            STEP_DEDUPE,
            records,
            messages,
            RULE_DEDUPE,
            require(clean, "clean_counts", "dedupe_precision"),
            require(clean, "clean_counts", "dedupe_recall"),
        ),
        (
            3,
            STEP_IDENTITY,
            addresses,
            entities,
            RULE_IDENTITY,
            require(identity, "identity_counts", "precision"),
            require(identity, "identity_counts", "recall"),
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
    occurrences: dict[str, int] = require(ingest, "ingest_counts", "header_fields")
    rulings: dict[str, str] = require(ingest, "ingest_counts", "header_rulings")
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
