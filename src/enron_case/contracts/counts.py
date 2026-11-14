"""Shapes of the counts-only side outputs each stage writes to the COUNTS zone.

Producers write these with `ctx.write_counts(name, ...)`; the release package reads them to
build `data_quality.csv` and `header_fields.csv`. Counts only: no address, name or value.
"""

from __future__ import annotations

from typing import TypedDict


class IngestCounts(TypedDict):
    files_seen: int
    files_parsed: int
    rejected: dict[str, int]  # reason -> files
    header_fields: dict[str, int]  # header field name -> occurrences (names only)
    header_rulings: dict[
        str, str
    ]  # field name -> usable | identifier | content | technical | dropped
    parse_flags: dict[str, int]


class CleanCounts(TypedDict):
    records_in: int
    messages_out: int
    removed_exact: int
    removed_subset: int
    flags: dict[str, int]  # message flag -> messages
    message_id_shared_share: float | None  # research R3 diagnostic
    dedupe_precision: float | None  # sample only (ground truth)
    dedupe_recall: float | None


class IdentityCounts(TypedDict):
    addresses: int
    entities: int
    entities_by_type: dict[str, int]
    merges_by_rule: dict[str, int]
    blocked_by_guard: dict[str, int]
    cluster_sizes: dict[str, int]  # cluster size -> number of clusters
    precision: float | None  # sample only (ground truth)
    recall: float | None
    manual_checked: int | None  # real corpus only (T046)
    manual_correct: int | None


class PseudoCounts(TypedDict):
    entities: int
    events: int
    messages_without_time: int
    events_in_network: int


COUNT_FILES = ("ingest_counts", "clean_counts", "identity_counts", "pseudo_counts")
