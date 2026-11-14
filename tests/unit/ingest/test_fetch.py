"""T021: download, resume and checksum verification, with an injected downloader."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from enron_case.errors import CorpusError
from enron_case.ingest.fetch import fetch_archive, partial_path

PAYLOAD = b"synthetic archive bytes " * 1000
SHA = hashlib.sha256(PAYLOAD).hexdigest()
URL = "https://example.invalid/corpus.tar.gz"


class FakeDownloader:
    """Serves PAYLOAD from the requested offset; optionally fails after `fail_after` bytes."""

    def __init__(self, payload: bytes = PAYLOAD, fail_after: int | None = None) -> None:
        self.payload = payload
        self.fail_after = fail_after
        self.offsets: list[int] = []

    def __call__(self, url: str, target: Path, offset: int) -> None:
        assert url == URL
        self.offsets.append(offset)
        assert target.stat().st_size == offset if target.exists() else offset == 0
        chunk = self.payload[offset:]
        if self.fail_after is not None:
            chunk = chunk[: self.fail_after]
        with target.open("ab") as out:
            out.write(chunk)
        if self.fail_after is not None:
            raise OSError("connection reset")


def test_downloads_and_verifies(tmp_path: Path) -> None:
    target = tmp_path / "corpus.tar.gz"
    download = FakeDownloader()
    fetch_archive(target, URL, SHA, download)
    assert target.read_bytes() == PAYLOAD
    assert download.offsets == [0]
    assert not partial_path(target).exists()


def test_existing_valid_archive_is_not_downloaded(tmp_path: Path) -> None:
    target = tmp_path / "corpus.tar.gz"
    target.write_bytes(PAYLOAD)
    download = FakeDownloader()
    fetch_archive(target, URL, SHA, download)
    assert download.offsets == []


def test_resumes_partial_download(tmp_path: Path) -> None:
    target = tmp_path / "corpus.tar.gz"
    with pytest.raises(CorpusError) as failed:
        fetch_archive(target, URL, SHA, FakeDownloader(fail_after=5000))
    assert failed.value.exit_code == 4
    assert partial_path(target).stat().st_size == 5000
    download = FakeDownloader()
    fetch_archive(target, URL, SHA, download)
    assert download.offsets == [5000]
    assert target.read_bytes() == PAYLOAD


def test_checksum_mismatch_exits_4_and_keeps_nothing(tmp_path: Path) -> None:
    target = tmp_path / "corpus.tar.gz"
    with pytest.raises(CorpusError) as failed:
        fetch_archive(target, URL, SHA, FakeDownloader(payload=b"tampered" * 10))
    assert failed.value.exit_code == 4
    assert not target.exists()
    assert not partial_path(target).exists()


def test_existing_archive_with_wrong_checksum_fails(tmp_path: Path) -> None:
    target = tmp_path / "corpus.tar.gz"
    target.write_bytes(b"not the corpus")
    with pytest.raises(CorpusError):
        fetch_archive(target, URL, SHA, FakeDownloader())


def test_complete_partial_is_finished_without_a_request(tmp_path: Path) -> None:
    # Interrupted after the last byte but before the rename: a range request from the end would
    # be refused (HTTP 416) on every rerun, so the finished partial is verified and kept.
    target = tmp_path / "corpus.tar.gz"
    partial_path(target).write_bytes(PAYLOAD)
    download = FakeDownloader()
    fetch_archive(target, URL, SHA, download)
    assert download.offsets == []
    assert target.read_bytes() == PAYLOAD
    assert not partial_path(target).exists()
