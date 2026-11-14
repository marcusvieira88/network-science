"""T024/T025: header_records against the synthetic reference answer and hand-built cases."""

from __future__ import annotations

import io
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from enron_case.contracts import vocab
from enron_case.ingest.parse import member_location, parse_archive, parse_member
from enron_case.ingest.stage import parse
from enron_case.manifest import fingerprint
from enron_case.synth import SynthOutput
from helpers import ctx_with_fixtures, scan

CONTENT_MARKERS = ["CANARYBODY", "CANARYSUBJ", "CANARYFOLDER", "CANARYFILE"]


def _member(text: str, path: str = "maildir/a-ann/inbox/1.") -> dict[str, object]:
    record, _, _ = parse_member(path, io.BytesIO(text.encode("latin-1")))
    assert record is not None
    return record


def test_stage_output_equals_reference(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("ingest", synth, tmp_path)
    parse(ctx)
    expected = synth.table("header_records")
    produced = ctx.read("header_records")
    assert produced.height == expected.height
    assert fingerprint(produced) == fingerprint(expected)


def test_stage_counts(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("ingest", synth, tmp_path)
    parse(ctx)
    counts = ctx.read_counts("ingest_counts")
    reference = synth.counts("ingest_counts")
    records = synth.table("header_records")
    n_files = records.height
    assert counts["files_seen"] == counts["files_parsed"] == n_files
    assert counts["rejected"] == {}
    assert counts["parse_flags"] == reference["parse_flags"]
    assert counts["header_rulings"] == reference["header_rulings"]
    fields = counts["header_fields"]
    for always in ("Message-ID", "Date", "From", "Subject", "X-From", "X-To", "X-Folder"):
        assert fields[always] == n_files, always
    assert fields["Bcc"] == int((records.get_column("bcc_addrs").list.len() > 0).sum())
    assert fields["Cc"] == int((records.get_column("cc_addrs").list.len() > 0).sum())


def test_no_content_marker_in_output_or_counts(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("ingest", synth, tmp_path)
    parse(ctx)
    assert scan(ctx.paths.data_root / "ingest", CONTENT_MARKERS) == {}
    assert scan(ctx.paths.data_root / "counts", CONTENT_MARKERS) == {}


def test_date_converted_to_utc() -> None:
    record = _member("Date: Mon, 14 May 2001 16:39:00 -0700 (PDT)\n\n")
    assert record["ts_utc"] == datetime(2001, 5, 14, 23, 39, tzinfo=UTC)
    assert record["date_raw_ok"] is True
    assert record["parse_flags"] == []


def test_date_out_of_range_is_not_rejected_here() -> None:
    record = _member("Date: Mon, 14 May 1980 16:39:00 -0800 (PST)\n\n")
    assert record["ts_utc"] == datetime(1980, 5, 15, 0, 39, tzinfo=UTC)


@pytest.mark.parametrize("header", ["Date: unknown date\n", "Date: \n", ""])
def test_bad_or_missing_date_is_null_and_flagged(header: str) -> None:
    record = _member(header + "From: a@x.com\n\n")
    assert record["ts_utc"] is None
    assert record["date_raw_ok"] is False
    assert record["parse_flags"] == ["bad_date"]


def test_address_lists_split_and_raw() -> None:
    record = _member(
        "From:  Ann@X.com \nTo: b@x.com, , C@x.com,\n\td@x.com\nCc: undisclosed-recipients:;\n"
        "X-To: \nX-cc: Bob B\n\n"
    )
    assert record["from_addr"] == "Ann@X.com"
    assert record["to_addrs"] == ["b@x.com", "C@x.com", "d@x.com"]
    assert record["cc_addrs"] == ["undisclosed-recipients:;"]
    assert record["bcc_addrs"] == []
    assert record["x_to"] is None
    assert record["x_cc"] == "Bob B"
    assert record["x_from"] is None
    assert record["message_id"] is None
    assert record["parse_flags"] == ["bad_date", "folded"]


def test_member_without_header_end_is_rejected() -> None:
    text = "Date: Mon, 14 May 2001 16:39:00 -0700\nFrom: a@x.com\nMerger: x\nCc: c@y.com"
    record, names, reason = parse_member("maildir/a-ann/inbox/1.", io.BytesIO(text.encode()))
    assert record is None
    assert names == []
    assert reason == "no_header_end"


def test_identity_fields_from_path() -> None:
    record = _member("\n", "maildir/lay-k/_sent_mail/12.")
    assert record["mailbox_owner"] == "lay-k"
    assert record["folder_class"] == "sent"
    assert record["file_id"] == vocab.file_id("maildir/lay-k/_sent_mail/12.")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("maildir/lay-k/inbox/1.", ("lay-k", "inbox")),
        ("maildir/lay-k/inbox/sub/folder/1.", ("lay-k", "inbox")),
        ("maildir/lay-k/1.", None),
        ("other/lay-k/inbox/1.", None),
        ("maildir//inbox/1.", None),
    ],
)
def test_member_location(path: str, expected: tuple[str, str] | None) -> None:
    assert member_location(path) == expected


def test_members_outside_maildir_are_rejected(tmp_path: Path) -> None:

    archive = tmp_path / "a.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, data in (
            ("maildir/a-ann/inbox/1.", b"From: a@x.com\n\nCANARYBODY"),
            ("README", b"hello"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        directory = tarfile.TarInfo("maildir/a-ann")
        directory.type = tarfile.DIRTYPE
        tar.addfile(directory)
    records, counts = parse_archive(archive)
    assert records.height == 1
    assert counts["files_seen"] == 2
    assert counts["files_parsed"] == 1
    assert counts["rejected"] == {"outside_maildir": 1}
    assert counts["header_rulings"] == {"From": "identifier"}
