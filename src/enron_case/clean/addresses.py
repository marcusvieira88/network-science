"""Rule N1 address normalisation: the single source for what a valid address is.

Ingest-side only: inputs and outputs here are addresses and must never be logged.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from enron_case.contracts import vocab as v

# Characters peeled off both ends until the string stops changing.
WRAPPING_CHARS = " \t\r\n\"'<>."
MAILTO_PREFIX = "mailto:"
VALID_ADDRESS = re.compile(r"^[^@\s<>()\[\],;:\"]+@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z0-9-]+$")


def clean_address(raw: str) -> str:
    """Lower-case and strip whitespace, quotes, angle brackets, `mailto:` and edge dots."""
    text = raw.lower()
    while True:
        stripped = text.strip(WRAPPING_CHARS).removeprefix(MAILTO_PREFIX)
        if stripped == text:
            return text
        text = stripped


def normalize_address(raw: str) -> str | None:
    """The normalised address, or None when it is empty or malformed."""
    text = clean_address(raw)
    return text if VALID_ADDRESS.match(text) else None


def resolve_recipients(
    to: Iterable[str], cc: Iterable[str], bcc: Iterable[str]
) -> tuple[dict[str, str], bool]:
    """Normalised recipients with their strongest role, and whether any was malformed.

    Empty placeholders are dropped silently; only non-empty malformed strings count as bad.
    """
    roles: dict[str, str] = {}
    bad = False
    for role, raws in (("to", to), ("cc", cc), ("bcc", bcc)):
        for raw in raws:
            addr = normalize_address(raw)
            if addr is None:
                bad = bad or clean_address(raw) != ""
                continue
            roles[addr] = strongest_role(roles.get(addr), role)
    return roles, bad


def strongest_role(current: str | None, candidate: str) -> str:
    """The stronger of two recipient roles (to > cc > bcc)."""
    if current is None or v.ROLE_STRENGTH[candidate] > v.ROLE_STRENGTH[current]:
        return candidate
    return current
