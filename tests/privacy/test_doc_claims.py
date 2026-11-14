"""The documents make no privacy promise the design does not keep."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DOCUMENTS = sorted(
    [
        REPO / "README.md",
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


@pytest.mark.parametrize("claim", sorted(OVERCLAIMS))
def test_no_document_overclaims(claim: str) -> None:
    pattern = OVERCLAIMS[claim]
    offending = [
        str(path.relative_to(REPO))
        for path in DOCUMENTS
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offending == [], f"{claim}: {offending}"


# Documents this repository generates (their templates): a mail connector with a metadata-only
# scope keeps bodies and attachments at the source, but `Subject`, which is content, still
# arrives and is discarded at the allowlist. So "content never leaves the source" overclaims.
TEMPLATES = sorted((REPO / "src" / "enron_case" / "report" / "templates").glob("*.md"))
CONTENT_STAYS_AT_SOURCE = re.compile(r"content\s+never\s+leaves?\s+the\s+source", re.IGNORECASE)
PRECISE_CLAIM = re.compile(
    r"bodies\s+and\s+attachments\s+never\s+leave\s+the\s+source", re.IGNORECASE
)
SUBJECT_ARRIVES = re.compile(
    r"`Subject`\s+still\s+arrives\s+and\s+is\s+discarded\s+at\s+the\s+allowlist"
)


def test_no_template_says_mail_content_never_leaves_the_source() -> None:
    offending = [
        path.name
        for path in TEMPLATES
        if CONTENT_STAYS_AT_SOURCE.search(path.read_text(encoding="utf-8"))
    ]
    assert offending == []


@pytest.mark.parametrize("name", ["decision-record.md", "slides.md"])
def test_connector_claim_says_what_stays_and_what_still_arrives(name: str) -> None:
    text = next(path for path in TEMPLATES if path.name == name).read_text(encoding="utf-8")
    assert PRECISE_CLAIM.search(text), name
    assert SUBJECT_ARRIVES.search(text), name
