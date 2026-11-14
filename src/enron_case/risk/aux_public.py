"""Attacker A1's auxiliary knowledge: their own naive parse of the public archive.

This simulates an outsider who downloads the public corpus and reads `From`, `To`, `Cc` and
`Date` from each file. It deliberately shares no code with `ingest` (the attacker does not have
our parser) and does no identity resolution: each lower-cased address is its own node. Like the
real parser, it reads each archive member only up to the blank line that ends the headers.

This is the only risk module that touches the archive. The result is held in memory and never
written or logged; only counts leave this module.
"""

from __future__ import annotations

import re
import tarfile
from datetime import UTC, date, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import IO

import polars as pl

from enron_case.context import StageContext
from enron_case.risk.features import EDGE_SCHEMA, clean_edges

ATTACKER_FIELDS = ("from", "to", "cc", "date")
RECIPIENT_FIELDS = ("to", "cc")
HEADER_ENCODING = "latin-1"
ADDRESS_SEPARATOR = ","
# RFC 5322 field name: printable ASCII except colon, no whitespace.
HEADER_NAME = re.compile(r"[\x21-\x39\x3b-\x7e]+")

MessageKey = tuple[str, str, tuple[str, ...]]


def load_aux_edges(ctx: StageContext) -> pl.DataFrame:
    """The attacker's weekly edge list `(week, src, dst)` over addresses."""
    edges = parse_archive(ctx.archive)
    ctx.log(f"[risk] attacker view: {edges.height} weekly ties")
    return edges


def parse_archive(archive: Path) -> pl.DataFrame:
    """Weekly edges from every distinct message in a `.tar.gz` maildir archive.

    Copies of one message in several folders are collapsed on (sender, Date text, recipients),
    which is what an attacker without our deduplication would reasonably do.
    """
    seen: set[MessageKey] = set()
    rows: list[tuple[date, str, str]] = []
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            stream = tar.extractfile(member)
            if stream is None:
                continue
            parsed = message_from_headers(read_headers(stream))
            if parsed is None or parsed[0] in seen:
                continue
            seen.add(parsed[0])
            rows.extend(message_edges(*parsed))
    return clean_edges(pl.DataFrame(rows, schema=EDGE_SCHEMA, orient="row"))


def read_headers(stream: IO[bytes]) -> dict[str, str]:
    """The attacker's fields from one member, reading no further than the end of the header
    block: a blank or whitespace-only line, or the first line that is not a header line.
    Folded continuation lines are joined; every other field is discarded unread."""
    fields: dict[str, str] = {}
    current: str | None = None
    for raw in iter(stream.readline, b""):
        line = raw.decode(HEADER_ENCODING).rstrip("\r\n")
        if not line.strip():
            break
        if line[0] in " \t":
            if current is not None:
                fields[current] += " " + line.strip()
            continue
        name, colon, value = line.partition(":")
        if not colon or not HEADER_NAME.fullmatch(name):
            # Not a header line, so the body has begun without a blank line: stop unread.
            break
        current = name.lower()
        if current in ATTACKER_FIELDS:
            fields[current] = value.strip()
        else:
            current = None
    return fields


def message_from_headers(fields: dict[str, str]) -> tuple[MessageKey, date] | None:
    """The message key (sender, Date text, sorted recipients) and its week, or None when the
    attacker cannot use the message."""
    senders = split_addresses(fields.get("from", ""))
    recipients = tuple(
        sorted({a for name in RECIPIENT_FIELDS for a in split_addresses(fields.get(name, ""))})
    )
    date_text = fields.get("date", "")
    week = parse_week(date_text)
    if len(senders) != 1 or not recipients or week is None:
        return None
    return (senders[0], date_text, recipients), week


def message_edges(message: MessageKey, week: date) -> list[tuple[date, str, str]]:
    sender, _, recipients = message
    return [(week, sender, recipient) for recipient in recipients]


def split_addresses(value: str) -> list[str]:
    """Lower-cased addresses in a header value; anything without `@` is ignored."""
    out = []
    for part in value.split(ADDRESS_SEPARATOR):
        address = part.strip()
        if "<" in address and ">" in address:
            address = address[address.index("<") + 1 : address.index(">")]
        address = address.strip().lower()
        if "@" in address:
            out.append(address)
    return out


def parse_week(date_text: str) -> date | None:
    """Monday of the UTC calendar week of a Date header, or None if it does not parse."""
    try:
        moment = parsedate_to_datetime(date_text)
        if moment.tzinfo is None:
            return None
        day = moment.astimezone(UTC).date()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    return day - timedelta(days=day.weekday())
