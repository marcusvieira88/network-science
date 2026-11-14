"""T065: the attacker's naive parser reads headers only, From/To/Cc/Date, no resolution."""

from __future__ import annotations

import io
from datetime import date

from enron_case.config import MAX_HEADER_BYTES
from enron_case.risk import aux_public
from enron_case.synth import SynthOutput

MEMBER = (
    b"Message-ID: <1.2@x>\r\n"
    b"Date: Mon, 14 May 2001 16:39:00 -0700 (PDT)\r\n"
    b"From: Ann.Lee@Example.org\r\n"
    b"To: bob@example.org,\r\n"
    b"\tcat@example.org\r\n"
    b"Cc: Dan <dan@example.org>, undisclosed-recipients:;\r\n"
    b"Bcc: eve@example.org\r\n"
    b"Subject: CANARYSUBJ secret\r\n"
    b"\r\n"
    b"CANARYBODY From: mallory@example.org\r\n"
)


def test_reads_only_the_attacker_fields_and_stops_at_the_blank_line() -> None:
    stream = io.BytesIO(MEMBER)
    fields = aux_public.read_headers(stream)
    assert set(fields) == {"date", "from", "to", "cc"}
    assert fields["to"] == "bob@example.org, cat@example.org"
    assert stream.read() == b"CANARYBODY From: mallory@example.org\r\n"  # never consumed


def test_reading_stops_at_the_header_byte_cap() -> None:
    """A crafted member with an endless header line is not read into memory whole."""
    stream = io.BytesIO(b"From: a@x.org\nTo: " + b"b" * (2 * MAX_HEADER_BYTES) + b"\n\n")
    fields = aux_public.read_headers(stream)
    assert stream.tell() <= MAX_HEADER_BYTES
    assert "to" not in fields


def test_message_key_and_week() -> None:
    parsed = aux_public.message_from_headers(aux_public.read_headers(io.BytesIO(MEMBER)))
    assert parsed is not None
    (sender, _, recipients), week = parsed
    assert sender == "ann.lee@example.org"  # lower-cased, nothing more
    assert recipients == ("bob@example.org", "cat@example.org", "dan@example.org")
    assert week == date(2001, 5, 14)  # 23:39 UTC on Monday 14 May


def test_unusable_messages_are_skipped() -> None:
    assert aux_public.message_from_headers({"from": "a@x", "date": "unknown date"}) is None
    no_recipients = {"from": "a@x", "date": "Mon, 14 May 2001 16:39:00 -0700"}
    assert aux_public.message_from_headers(no_recipients) is None


def test_archive_parse_collapses_copies(synth: SynthOutput) -> None:
    edges = aux_public.parse_archive(synth.archive)
    truth = synth.truth()
    assert edges.columns == ["week", "src", "dst"]
    assert edges.filter(edges["src"] == edges["dst"]).height == 0
    assert edges.is_unique().all()
    nodes = set(edges["src"]) | set(edges["dst"])
    # No identity resolution: alias addresses stay separate nodes.
    assert nodes <= set(truth["address_to_truth"])
    assert len(nodes) > len({truth["address_to_truth"][a] for a in nodes})


def test_whitespace_only_line_ends_the_header_block() -> None:
    # A blank line holding only spaces ends the headers, as in the ingest reader; a forwarded
    # header in the body below it must never be read.
    member = (
        b"Date: Mon, 14 May 2001 16:39:00 -0700\r\n"
        b"From: a@example.org\r\n"
        b"   \r\n"
        b"To: mallory@example.org\r\n"
    )
    stream = io.BytesIO(member)
    fields = aux_public.read_headers(stream)
    assert "to" not in fields
    assert stream.read() == b"To: mallory@example.org\r\n"


def test_a_line_that_is_not_a_header_stops_the_reader() -> None:
    # No blank line at all: the first non-header line is body text; stop there.
    member = (
        b"Date: Mon, 14 May 2001 16:39:00 -0700\r\n"
        b"From: a@example.org\r\n"
        b"CANARYBODY no colon here\r\n"
        b"To: mallory@example.org\r\n"
    )
    stream = io.BytesIO(member)
    fields = aux_public.read_headers(stream)
    assert set(fields) == {"date", "from"}
    assert stream.read() == b"To: mallory@example.org\r\n"


def test_out_of_range_date_is_unusable_not_a_crash() -> None:
    # Parses, but lies past datetime.max once converted to UTC.
    assert aux_public.parse_week("Fri, 31 Dec 9999 23:00:00 -0200") is None
