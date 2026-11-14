"""Release tables to one JSON document for the explorer UI (research R14).

Shape of `release.json` (format_version 2; 2 added `windows`); `ui/src/lib/data.ts` mirrors it:

    {
      "format_version": 2,
      "contract_version": "<schemas.CONTRACT_VERSION>",
      "run": {"code_version": str, "sample": bool, "seed": int, "parameters": {...}},
      "events": [{"date": "YYYY-MM-DD", "label": str}, ...],      # config.PUBLIC_EVENTS
      "windows": {"crisis": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
                  "reference": {...}},          # config.CRISIS_WINDOW, config.REFERENCE_WINDOW
      "tables": {"<release table>": [{"<column>": value, ...}, ...], ...}
    }

The tables are `RELEASE_TABLES`, among them `artifact_checks` (hypothesis, check, statistic,
ci_low, ci_high, n_units, passes, note; `passes` is null when the check could not run) and
`exploratory` (E1–E20, docs/hypotheses-exploratory.md: order, hypothesis, family, measure,
direction, custodians, median_change, ci_low, ci_high, p, p_holm, placebo_custodians,
placebo_median, placebo_ci_low, placebo_ci_high, placebo_passes, loo_stable, outcome, caveat,
equalised_median, equalised_ci_low, equalised_ci_high, equalised_p; `caveat` is "" when there is
none and the `equalised_*` cells are null unless computed).

Rows keep the contract's column order and sort order; dates are ISO strings; suppressed cells
and non-finite numbers (NaN, ±inf: not computable) are null. The run block is the run manifest
without wall-clock time, timings or fingerprints, so the same release gives byte-identical JSON.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterator
from datetime import date
from typing import Any

import polars as pl

from enron_case.config import CRISIS_WINDOW, PUBLIC_EVENTS, REFERENCE_WINDOW
from enron_case.contracts import schemas
from enron_case.contracts.vocab import LEAK_PATTERNS
from enron_case.errors import ContractViolation, PrivacyViolation

FORMAT_VERSION = 2

RELEASE_TABLES = (
    "data_quality",
    "header_fields",
    "weekly_metrics",
    "hypotheses",
    "artifact_checks",
    "exploratory",
    "risk",
    "degree_distribution",
    "community_graph",
    "community_groups",
)

MANIFEST_RUN_FIELDS = ("code_version", "sample", "seed", "parameters")

_LEAK = re.compile("|".join(f"(?:{pattern})" for pattern in LEAK_PATTERNS))

Row = dict[str, Any]


def check_person_counts(tables: dict[str, pl.DataFrame], k_min: int) -> None:
    """Raise PrivacyViolation if any published person count is below k_min."""
    for name, df in tables.items():
        small = schemas.person_counts_below(name, df, k_min)
        if small:
            raise PrivacyViolation(f"{name}: {small} person counts below k={k_min}")


def table_rows(df: pl.DataFrame) -> list[Row]:
    return [
        {key: _jsonable(value) for key, value in row.items()} for row in df.iter_rows(named=True)
    ]


def _jsonable(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None  # NaN or ±inf: not computable; JSON has no such number
    return value


def run_block(manifest: dict[str, Any]) -> dict[str, Any]:
    missing = [name for name in MANIFEST_RUN_FIELDS if name not in manifest]
    if missing:
        raise ContractViolation(f"run manifest lacks {missing}")
    return {name: manifest[name] for name in MANIFEST_RUN_FIELDS}


def build_document(tables: dict[str, pl.DataFrame], manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "format_version": FORMAT_VERSION,
        "contract_version": schemas.CONTRACT_VERSION,
        "run": run_block(manifest),
        "events": [{"date": day.isoformat(), "label": label} for day, label in PUBLIC_EVENTS],
        "windows": {
            "crisis": window_block(CRISIS_WINDOW),
            "reference": window_block(REFERENCE_WINDOW),
        },
        "tables": {name: table_rows(tables[name]) for name in RELEASE_TABLES},
    }


def window_block(window: tuple[date, date]) -> dict[str, str]:
    start, end = window
    return {"start": start.isoformat(), "end": end.isoformat()}


def strings(value: object) -> Iterator[str]:
    """Every string in a JSON-like value, keys included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def check_no_identifiers(document: dict[str, Any]) -> None:
    hits = sum(1 for text in strings(document) if _LEAK.search(text))
    if hits:
        raise PrivacyViolation(f"release.json: {hits} identifier-shaped values")


def render(document: dict[str, Any]) -> str:
    """Compact JSON text. Key order is fixed by construction, so no wall-clock or hash order
    can change the bytes."""
    try:
        return json.dumps(document, separators=(",", ":"), allow_nan=False) + "\n"
    except ValueError as exc:
        raise ContractViolation("release.json would contain a non-finite number") from exc
