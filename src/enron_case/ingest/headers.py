"""Header-block reader: the only code that touches the bytes of a message.

It reads a member line by line up to the first blank (or whitespace-only) line and never further.
It also stops at the first line that is neither a continuation nor a valid `Name: value` header
line, after MAX_HEADER_LINES lines, and after config.MAX_HEADER_BYTES bytes; in all these cases
the block is marked not ended and the caller rejects the member, so body text can never be taken
for header fields. Each physical line
is classified by field name as soon as it is read; the value of a field that is not kept is
discarded with that line, so no dropped value outlives the loop iteration that read it.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import IO

from enron_case.config import MAX_HEADER_BYTES

ENCODING = "latin-1"
CONTINUATION_START = (" ", "\t")
LINE_END = "\r\n"
# Upper bound on physical header lines; the longest real header (a folded list of several
# hundred recipients) stays far below it.
MAX_HEADER_LINES = 5000
# RFC 5322 field name: printable ASCII except colon, no whitespace.
FIELD_NAME = re.compile(r"[\x21-\x39\x3b-\x7e]+")


@dataclass
class HeaderBlock:
    """Kept fields (unfolded, in file order) and the name of every field seen."""

    fields: list[tuple[str, str]] = field(default_factory=list)
    names_seen: list[str] = field(default_factory=list)
    folded: bool = False
    ended: bool = False


def read_header(stream: IO[bytes], keep: Collection[str]) -> HeaderBlock:
    """Read the header block of one message. `keep` holds lower-case field names to retain.

    Stops after the first blank or whitespace-only line (`ended`). Stops with `ended` false at
    end of stream, at a line that is not a header line, after MAX_HEADER_LINES lines, or at a
    line cut short by MAX_HEADER_BYTES.
    """
    block = HeaderBlock()
    keeping = False
    lines = 0
    budget = MAX_HEADER_BYTES
    while lines < MAX_HEADER_LINES and budget and (raw := stream.readline(budget)):
        lines += 1
        budget -= len(raw)
        if not budget and not raw.endswith(b"\n"):
            break
        line = raw.decode(ENCODING).rstrip(LINE_END)
        if not line.strip():
            block.ended = True
            break
        if line.startswith(CONTINUATION_START):
            if keeping:
                name, value = block.fields[-1]
                block.fields[-1] = (name, f"{value} {line.lstrip()}")
                block.folded = True
            continue
        name, colon, value = line.partition(":")
        if not colon or not FIELD_NAME.fullmatch(name):
            break
        block.names_seen.append(name)
        keeping = name.lower() in keep
        if keeping:
            block.fields.append((name, value.strip()))
    return block
