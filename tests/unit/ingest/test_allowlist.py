"""T020: the allowlist in code equals the contract, and dropped fields never come back."""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

from enron_case.contracts import vocab
from enron_case.ingest import allowlist
from enron_case.ingest.parse import parse_member

CONTRACT = (
    Path(__file__).resolve().parents[3]
    / "specs/001-enron-network-analysis/contracts/header-allowlist.md"
)
# The contract lists X-Origin as "ingest only → is_custodian", but the WP-A brief drops it at
# the parser because the archive path already names the mailbox owner (reported to the lead).
RETAINED_BY_CONTRACT_BUT_DROPPED_BY_BRIEF = {"X-Origin"}

SAMPLE = (
    "Message-ID: <1.2.JavaMail.evans@thyme>\n"
    "Date: Mon, 14 May 2001 16:39:00 -0700 (PDT)\n"
    "From: a@acme-energy.com\n"
    "To: b@acme-energy.com, c@acme-energy.com\n"
    "Subject: Re: CANARYSUBJ quarterly\n"
    "Mime-Version: 1.0\n"
    "Content-Type: text/plain; charset=us-ascii\n"
    "Content-Transfer-Encoding: 7bit\n"
    "X-From: Ann A\n"
    "X-To: Bob B, Cat C\n"
    "X-cc: \n"
    "X-bcc: \n"
    "X-Folder: \\Ann_A_May2001\\Notes Folders\\CANARYFOLDER\n"
    "X-Origin: A-ANN\n"
    "X-FileName: aann CANARYFILE (Non-Privileged).pst\n"
    "X-Unknown-Thing: CANARYUNKNOWN\n"
    "\n"
    "CANARYBODY text\n"
)


def _contract_retained() -> set[str]:
    """Field names of the *usable* rows and the rows that reach *ingest only*."""
    retained: set[str] = set()
    for line in CONTRACT.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 4 or not cells[0].startswith("`"):
            continue
        field, ruling, reaches = cells[0], cells[1], cells[2]
        if ruling.startswith("usable") or reaches.startswith("ingest only"):
            retained.update(re.findall(r"`([^`]+)`", field))
    return retained


def test_contract_parser_finds_rows() -> None:
    assert {"Date", "From", "X-bcc", "Message-ID"} <= _contract_retained()


def test_retained_names_equal_contract() -> None:
    expected = _contract_retained() - RETAINED_BY_CONTRACT_BUT_DROPPED_BY_BRIEF
    assert set(allowlist.RETAINED) == expected


def test_rulings_cover_every_contract_field() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    for name in allowlist.RULINGS:
        assert f"`{name}`" in text, name
    assert allowlist.RULINGS["Subject"] == "content"
    assert allowlist.RULINGS["X-Folder"] == "content"
    assert allowlist.RULINGS["Date"] == "usable"
    assert allowlist.RULINGS["Message-ID"] == "technical"


@pytest.mark.parametrize("name", sorted(allowlist.RETAINED))
def test_retained_fields_are_usable_identifier_or_technical(name: str) -> None:
    assert allowlist.RULINGS[name] in {"usable", "identifier", "technical"}


def test_unknown_field_is_dropped_and_case_is_ignored() -> None:
    assert allowlist.ruling("X-Brand-New") == "dropped"
    assert allowlist.ruling("subject") == "content"
    assert allowlist.ruling("x-CC") == allowlist.RULINGS["X-cc"]
    assert allowlist.canonical("message-id") == "Message-ID"
    assert allowlist.canonical("X-Brand-New") == "X-Brand-New"


def test_retain_keeps_first_occurrence_under_canonical_name() -> None:
    kept = allowlist.retain([("from", "a@x"), ("Subject", "s"), ("FROM", "b@x")])
    assert kept == {"From": "a@x"}


def test_dropped_fields_never_appear_in_returned_record() -> None:
    record, names, _ = parse_member(
        "maildir/a-ann/canaryfolder_projects/1.", io.BytesIO(SAMPLE.encode("latin-1"))
    )
    assert record is not None
    text = repr(record)
    for marker in ("CANARY", "quarterly", "Mime", "text/plain", "7bit", "A-ANN", ".pst"):
        assert marker not in text, marker
    assert "Subject" in names and "X-FileName" in names and "X-Unknown-Thing" in names


@pytest.mark.parametrize(
    ("folder", "expected"),
    [
        ("_sent_mail", "sent"),
        ("sent_items", "sent"),
        ("inbox", "inbox"),
        ("deleted_items", "deleted"),
        ("canaryfolder_projects", "other"),
        ("all_documents", "other"),
    ],
)
def test_folder_reduced_to_class(folder: str, expected: str) -> None:
    record, _, _ = parse_member(f"maildir/a-ann/{folder}/7.", io.BytesIO(SAMPLE.encode("latin-1")))
    assert record is not None
    assert record["folder_class"] == expected
    assert record["folder_class"] in vocab.FOLDER_CLASSES
    assert folder not in repr(record) or folder == expected


def test_identifiers_not_retained_are_exactly_the_identifier_fields_the_parser_drops() -> None:
    """The report's legend names these fields from `vocab`; the allowlist is the source."""
    dropped = {
        name
        for name, ruling in allowlist.RULINGS.items()
        if ruling == allowlist.IDENTIFIER and name not in allowlist.RETAINED
    }
    assert set(vocab.IDENTIFIERS_NOT_RETAINED) == dropped
