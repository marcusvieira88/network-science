"""T019: the header reader stops at the end of the header block and never reads a body."""

from __future__ import annotations

import io

from hypothesis import given
from hypothesis import strategies as st

from enron_case.config import MAX_HEADER_BYTES
from enron_case.ingest.headers import MAX_HEADER_LINES, read_header

KEEP_ALL = frozenset({"from", "to", "subject", "x-to"})


class CountingStream(io.BytesIO):
    """A stream that records how many bytes the reader took from it."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.consumed = 0

    def readline(self, size: int | None = -1, /) -> bytes:
        line = super().readline(size)
        self.consumed += len(line)
        return line

    def read(self, size: int | None = -1, /) -> bytes:
        data = super().read(size)
        self.consumed += len(data)
        return data


def test_stops_at_first_blank_line_and_consumes_no_body_bytes() -> None:
    header = b"From: a@x.com\nTo: b@x.com\n\n"
    body = b"CANARYBODY " * 1_000_000
    stream = CountingStream(header + body)
    block = read_header(stream, KEEP_ALL)
    assert stream.consumed == len(header)
    assert block.ended
    assert block.fields == [("From", "a@x.com"), ("To", "b@x.com")]


def test_crlf_blank_line_ends_header() -> None:
    header = b"From: a@x.com\r\n\r\n"
    stream = CountingStream(header + b"body\r\n")
    block = read_header(stream, KEEP_ALL)
    assert stream.consumed == len(header)
    assert block.fields == [("From", "a@x.com")]


def test_unfolds_continuation_lines() -> None:
    stream = io.BytesIO(b"To: a@x.com,\n\tb@x.com,\n   c@x.com\nFrom: d@x.com\n\nbody")
    block = read_header(stream, KEEP_ALL)
    assert block.fields == [("To", "a@x.com, b@x.com, c@x.com"), ("From", "d@x.com")]
    assert block.folded


def test_unfolded_header_is_not_flagged_folded() -> None:
    block = read_header(io.BytesIO(b"To: a@x.com\n\n"), KEEP_ALL)
    assert not block.folded


def test_folding_of_a_dropped_field_does_not_flag_folded() -> None:
    block = read_header(io.BytesIO(b"Subject: one\n two\nTo: a@x.com\n\n"), frozenset({"to"}))
    assert not block.folded
    assert block.fields == [("To", "a@x.com")]


def test_decodes_latin1() -> None:
    block = read_header(io.BytesIO("X-To: Jürgen Größ\n\n".encode("latin-1")), KEEP_ALL)
    assert block.fields == [("X-To", "Jürgen Größ")]


def test_flags_member_with_no_header_end() -> None:
    block = read_header(io.BytesIO(b"From: a@x.com\nTo: b@x.com"), KEEP_ALL)
    assert not block.ended
    assert block.fields == [("From", "a@x.com"), ("To", "b@x.com")]


def test_dropped_values_are_not_returned_but_names_are_counted() -> None:
    raw = b"Subject: CANARYSUBJ\nX-Folder: CANARYFOLDER\nFrom: a@x.com\n\n"
    block = read_header(io.BytesIO(raw), frozenset({"from"}))
    assert block.fields == [("From", "a@x.com")]
    assert block.names_seen == ["Subject", "X-Folder", "From"]
    assert "CANARY" not in repr(block)


def test_empty_value_is_kept_as_empty_string() -> None:
    block = read_header(io.BytesIO(b"X-To: \n\n"), KEEP_ALL)
    assert block.fields == [("X-To", "")]


def test_line_without_colon_ends_the_block_unended() -> None:
    block = read_header(io.BytesIO(b"From: a@x.com\ngarbage line\nCc: c@x.com\n\n"), KEEP_ALL)
    assert not block.ended
    assert block.names_seen == ["From"]


def test_whitespace_only_line_ends_the_header() -> None:
    raw = b"From: a@x.com\nTo: b@x.com\n \nMerger: CANARYBODY\nCc: lawyer@y.com\n"
    block = read_header(io.BytesIO(raw), KEEP_ALL)
    assert block.ended
    assert block.names_seen == ["From", "To"]


def test_line_cap_stops_reading() -> None:
    raw = b"From: a@x.com\n" + b"X-A: 1\n" * (MAX_HEADER_LINES + 10) + b"\n"
    stream = io.BytesIO(raw)
    block = read_header(stream, KEEP_ALL)
    assert not block.ended
    assert len(block.names_seen) == MAX_HEADER_LINES


def test_byte_cap_stops_a_line_without_end() -> None:
    """A header line longer than the cap (a crafted member with no newline) is never read whole."""
    raw = b"From: a@x.com\nX-Long: " + b"a" * (2 * MAX_HEADER_BYTES) + b"\n\nCANARYBODY"
    stream = CountingStream(raw)
    block = read_header(stream, KEEP_ALL)
    assert not block.ended
    assert stream.consumed <= MAX_HEADER_BYTES


def test_byte_cap_bounds_folded_continuations() -> None:
    line = b" " + b"b" * 1000 + b"\n"
    raw = b"To: a@x.com\n" + line * (2 * MAX_HEADER_BYTES // len(line)) + b"\n"
    stream = CountingStream(raw)
    block = read_header(stream, KEEP_ALL)
    assert not block.ended
    assert stream.consumed <= MAX_HEADER_BYTES


def test_line_whose_prefix_is_not_a_field_name_stops_reading() -> None:
    raw = b"From: a@x.com\nNote from Ann: CANARYBODY\nX-To: b\n\n"
    block = read_header(io.BytesIO(raw), KEEP_ALL)
    assert not block.ended
    assert block.names_seen == ["From"]
    assert block.fields == [("From", "a@x.com")]


_name = st.sampled_from(["From", "To", "Subject", "X-To", "X-Weird"])
_word = st.text(alphabet="abcdefghij@.", min_size=1, max_size=8)


@given(
    fields=st.lists(st.tuples(_name, st.lists(_word, min_size=1, max_size=4)), max_size=8),
    fold=st.lists(st.booleans(), min_size=8, max_size=8),
    body=st.binary(max_size=200),
)
def test_property_header_body_split(
    fields: list[tuple[str, list[str]]], fold: list[bool], body: bytes
) -> None:
    """Any header with any folding and any body: unfolded fields come back exactly, kept
    ones only, and not one body byte is consumed."""
    lines = []
    expected = []
    any_folded_kept = False
    for (name, words), folded in zip(fields, fold, strict=False):
        joiner = ",\n\t" if folded else ", "
        lines.append(f"{name}: " + joiner.join(words))
        if name.lower() in KEEP_ALL:
            expected.append((name, ", ".join(words)))
            any_folded_kept = any_folded_kept or (folded and len(words) > 1)
    header = ("\n".join(lines) + "\n\n").encode("latin-1") if lines else b"\n"
    stream = CountingStream(header + b"CANARYBODY" + body)
    block = read_header(stream, KEEP_ALL)
    assert stream.consumed == len(header)
    assert block.ended
    assert block.fields == expected
    assert block.folded == any_folded_kept
    assert block.names_seen == [name for name, _ in fields]
