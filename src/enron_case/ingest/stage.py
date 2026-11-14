"""Ingest stages: `fetch` (corpus download) and `parse` (headers only)."""

from __future__ import annotations

from enron_case.config import CORPUS_ARCHIVE, CORPUS_SHA256, CORPUS_URL
from enron_case.context import StageContext
from enron_case.ingest.fetch import fetch_archive
from enron_case.ingest.parse import TABLE, parse_archive
from enron_case.zones import Zone

COUNTS_NAME = "ingest_counts"


def fetch(ctx: StageContext) -> None:
    target = ctx.path(Zone.RAW, CORPUS_ARCHIVE, "w")
    fetch_archive(target, CORPUS_URL, CORPUS_SHA256)
    ctx.log("[fetch] corpus archive verified")


def parse(ctx: StageContext) -> None:
    records, counts = parse_archive(ctx.archive)
    ctx.write(TABLE, records)
    ctx.write_counts(COUNTS_NAME, dict(counts))
    ctx.log(
        f"[parse] {counts['files_parsed']} of {counts['files_seen']} files parsed, "
        f"{sum(counts['rejected'].values())} rejected, "
        f"{len(counts['header_fields'])} distinct header fields"
    )
