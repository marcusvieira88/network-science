"""Header allowlist (specs/001-enron-network-analysis/contracts/header-allowlist.md).

Single source of which header fields the parser keeps. Every other field's value is dropped
at the reader; only its name is counted. The fixed folder vocabulary lives in
`contracts.vocab` (FOLDER_VOCAB, folder_class) because consumers share it.
"""

from __future__ import annotations

from collections.abc import Iterable

from enron_case.contracts.vocab import OTHER_HEADER_FIELD

USABLE = "usable"
IDENTIFIER = "identifier"
CONTENT = "content"
TECHNICAL = "technical"
DROPPED = "dropped"

RULINGS: dict[str, str] = {
    "Date": USABLE,
    "From": IDENTIFIER,
    "To": IDENTIFIER,
    "Cc": IDENTIFIER,
    "Bcc": IDENTIFIER,
    "X-From": IDENTIFIER,
    "X-To": IDENTIFIER,
    "X-cc": IDENTIFIER,
    "X-bcc": IDENTIFIER,
    # The archive path names the owner, so X-Origin adds nothing and is dropped.
    "X-Origin": IDENTIFIER,
    "X-Folder": CONTENT,
    "Subject": CONTENT,
    "Message-ID": TECHNICAL,
    "X-FileName": IDENTIFIER,
    "Mime-Version": DROPPED,
    "Content-Type": DROPPED,
    "Content-Transfer-Encoding": DROPPED,
}

RETAINED: tuple[str, ...] = (
    "Date",
    "From",
    "To",
    "Cc",
    "Bcc",
    "X-From",
    "X-To",
    "X-cc",
    "X-bcc",
    "Message-ID",
)
# Lower-case names handed to the header reader.
KEEP_NAMES: frozenset[str] = frozenset(name.lower() for name in RETAINED)

_CANONICAL: dict[str, str] = {name.lower(): name for name in RULINGS}


def canonical(name: str) -> str:
    """Contract spelling of a known field name; unknown names are returned as seen."""
    return _CANONICAL.get(name.lower(), name)


def counted_name(name: str) -> str:
    """Name under which a field is counted: its contract spelling if ruled on, else
    OTHER_HEADER_FIELD. An unknown "name" can be a fragment of message text, so its spelling is
    never kept, not even in the counts zone."""
    key = canonical(name)
    return key if key in RULINGS else OTHER_HEADER_FIELD


def ruling(name: str) -> str:
    """Ruling of a field name, case-insensitive. Unknown names are dropped (default deny)."""
    return RULINGS.get(canonical(name), DROPPED)


def retain(fields: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Allowlisted fields under their contract names; the first occurrence of a name wins."""
    kept: dict[str, str] = {}
    for name, value in fields:
        key = canonical(name)
        if key in RETAINED and key not in kept:
            kept[key] = value
    return kept
