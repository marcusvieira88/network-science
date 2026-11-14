"""The documents make no privacy promise the design does not keep."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DOCUMENTS = sorted(
    [
        REPO / "README.md",
        REPO / "AGENTS.md",
        REPO / "ui" / "README.md",
        REPO / ".specify" / "memory" / "constitution.md",
        *(REPO / ".claude" / "skills").glob("*-review/SKILL.md"),
        *(REPO / "docs").rglob("*.md"),
        *(REPO / "specs").rglob("*.md"),
        *(REPO / "src" / "enron_case" / "report" / "templates").glob("*.md"),
    ]
)

# Claims stronger than the design: Teams and Slack have no metadata-only scope, so their
# connectors receive message text and only our code drops it.
OVERCLAIMS = {
    "every connector keeps content at the source": re.compile(
        r"connectors\W*\s+so\s+content\s+never\s+leaves\s+the\s+source", re.IGNORECASE
    ),
    "Slack returns header fields only": re.compile(
        r"Slack\s+APIs?\s+request\s+header\s+fields\s+only", re.IGNORECASE
    ),
}


def test_every_listed_document_exists() -> None:
    assert [str(path.relative_to(REPO)) for path in DOCUMENTS if not path.is_file()] == []


@pytest.mark.parametrize("claim", sorted(OVERCLAIMS))
def test_no_document_overclaims(claim: str) -> None:
    pattern = OVERCLAIMS[claim]
    offending = [
        str(path.relative_to(REPO))
        for path in DOCUMENTS
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offending == [], f"{claim}: {offending}"
