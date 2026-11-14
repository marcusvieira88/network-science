"""Build `header_records` and `ingest_counts` from the archive, reading headers only."""

from __future__ import annotations

import tarfile
from collections import Counter
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import IO

import polars as pl

from enron_case.contracts import schemas, vocab
from enron_case.contracts.counts import IngestCounts
from enron_case.errors import ContractViolation, CorpusError
from enron_case.ingest import allowlist
from enron_case.ingest.headers import read_header

MAILDIR_ROOT = "maildir"
# root / owner / folder / file at least
MIN_PATH_PARTS = 4
REJECT_OUTSIDE_MAILDIR = "outside_maildir"
REJECT_NO_HEADER_END = "no_header_end"
ADDRESS_SEPARATOR = ","
# Rows per DataFrame batch; keeps Python row objects bounded on the 517k-member corpus.
TABLE = "header_records"

ADDRESS_FIELDS = {"To": "to_addrs", "Cc": "cc_addrs", "Bcc": "bcc_addrs"}
OPTIONAL_FIELDS = {
    "From": "from_addr",
    "X-From": "x_from",
    "X-To": "x_to",
    "X-cc": "x_cc",
    "X-bcc": "x_bcc",
    "Message-ID": "message_id",
}

Record = dict[str, object]


def member_location(member_path: str) -> tuple[str, str] | None:
    """(mailbox owner, raw top-level folder) of `maildir/<owner>/<folder>/.../<n>.`, else None."""
    parts = member_path.split("/")
    if len(parts) < MIN_PATH_PARTS or parts[0] != MAILDIR_ROOT or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def parse_date(value: str | None) -> datetime | None:
    """`Date` header as an aware UTC datetime, or None if absent or unparseable."""
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            # RFC 5322 "-0000": the instant is UTC, the sender's zone unknown.
            return parsed.replace(tzinfo=UTC)
        # Inside the try: a date at the edge of the range overflows on conversion.
        return parsed.astimezone(UTC)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def split_addresses(value: str | None) -> list[str]:
    if value is None:
        return []
    return [part.strip() for part in value.split(ADDRESS_SEPARATOR) if part.strip()]


def parse_member(
    member_path: str, stream: IO[bytes]
) -> tuple[Record | None, list[str], str | None]:
    """One `header_records` row, the names of every header field seen, and a reject reason.

    A member outside the maildir layout, or whose header block does not end cleanly, is
    rejected (record None): without a clean end, body lines could pass for header fields.
    """
    location = member_location(member_path)
    if location is None:
        return None, [], REJECT_OUTSIDE_MAILDIR
    owner, raw_folder = location
    block = read_header(stream, allowlist.KEEP_NAMES)
    if not block.ended:
        return None, [], REJECT_NO_HEADER_END
    kept = allowlist.retain(block.fields)
    ts_utc = parse_date(kept.get("Date"))
    flags = []
    if ts_utc is None:
        flags.append("bad_date")
    if block.folded:
        flags.append("folded")
    record: Record = {
        "file_id": vocab.file_id(member_path),
        "mailbox_owner": owner,
        "folder_class": vocab.folder_class(raw_folder),
        "date_raw_ok": ts_utc is not None,
        "ts_utc": ts_utc,
        "parse_flags": sorted(flags),
    }
    for name, column in ADDRESS_FIELDS.items():
        record[column] = split_addresses(kept.get(name))
    for name, column in OPTIONAL_FIELDS.items():
        record[column] = kept.get(name) or None
    return record, block.names_seen, None


def parse_archive(archive: Path, batch_rows: int) -> tuple[pl.DataFrame, IngestCounts]:
    """Stream the archive once; return `header_records` (conformed) and the ingest counts.
    Parsed rows become a table every `batch_rows` rows, which bounds memory."""
    schema = schemas.table(TABLE).polars_schema
    batches: list[pl.DataFrame] = []
    rows: list[Record] = []
    fields: Counter[str] = Counter()
    flags: Counter[str] = Counter()
    rejected: Counter[str] = Counter()
    files_seen = 0
    try:
        with tarfile.open(archive, "r|gz") as tar:
            for member in tar:
                if not member.isfile():
                    continue
                files_seen += 1
                stream = tar.extractfile(member)
                if stream is None:
                    raise CorpusError("archive member could not be opened")
                with stream:
                    record, names, reason = parse_member(member.name, stream)
                if record is None:
                    rejected[reason or REJECT_OUTSIDE_MAILDIR] += 1
                    continue
                fields.update(allowlist.canonical(name) for name in names)
                parse_flags = record["parse_flags"]
                if not isinstance(parse_flags, list):
                    raise ContractViolation("header record: parse_flags is not a list")
                flags.update(str(flag) for flag in parse_flags)
                rows.append(record)
                if len(rows) >= batch_rows:
                    batches.append(pl.DataFrame(rows, schema=schema))
                    rows = []
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise CorpusError("archive could not be read") from exc
    batches.append(pl.DataFrame(rows, schema=schema))
    counts: IngestCounts = {
        "files_seen": files_seen,
        "files_parsed": sum(batch.height for batch in batches),
        "rejected": dict(sorted(rejected.items())),
        "header_fields": dict(sorted(fields.items())),
        "header_rulings": {name: allowlist.ruling(name) for name in sorted(fields)},
        "parse_flags": dict(sorted(flags.items())),
    }
    return schemas.conform(pl.concat(batches), TABLE), counts
