"""Header-block reader: the only code that touches the bytes of a message.

It reads a member line by line up to the first blank line and never further. Each physical line
is classified by field name as soon as it is read; the value of a field that is not kept is
discarded with that line, so no dropped value outlives the loop iteration that read it.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import IO

ENCODING = "latin-1"
CONTINUATION_START = (" ", "\t")
LINE_END = "\r\n"
# RFC 5322 field name: printable ASCII except colon, no whitespace. Anything else is not a
# header line, so a body-like line in a member without a header end is never counted as a name.
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

    Stops after the first blank line (`ended`), or at end of stream (`ended` false).
    """
    block = HeaderBlock()
    keeping = False
    while raw := stream.readline():
        line = raw.decode(ENCODING).rstrip(LINE_END)
        if not line:
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
            keeping = False
            continue
        block.names_seen.append(name)
        keeping = name.lower() in keep
        if keeping:
            block.fields.append((name, value.strip()))
    return block
