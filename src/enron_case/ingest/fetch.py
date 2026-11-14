"""Download the corpus archive to the raw zone, resuming a partial download, and verify its
pinned SHA-256."""

from __future__ import annotations

import shutil
import urllib.error
import urllib.request
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path

from enron_case.errors import CorpusError
from enron_case.manifest import file_sha256

PARTIAL_SUFFIX = ".part"
HASH_CHUNK_BYTES = 1 << 20

# (url, target, offset): append the bytes of `url` from `offset` onward to `target`.
Downloader = Callable[[str, Path, int], None]


def partial_path(target: Path) -> Path:
    return target.with_name(target.name + PARTIAL_SUFFIX)


def http_downloader(timeout_seconds: int) -> Downloader:
    """`http_download` with a socket timeout."""

    def download(url: str, target: Path, offset: int) -> None:
        http_download(url, target, offset, timeout_seconds)

    return download


def http_download(url: str, target: Path, offset: int, timeout_seconds: int) -> None:
    """Append `url` to `target` from `offset`, using an HTTP Range request when resuming.
    A server that ignores the range sends the whole file, which then replaces `target`."""
    request = urllib.request.Request(url)
    if offset:
        request.add_header("Range", f"bytes={offset}-")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        resumed = response.status == HTTPStatus.PARTIAL_CONTENT
        with target.open("ab" if resumed else "wb") as out:
            shutil.copyfileobj(response, out, HASH_CHUNK_BYTES)


def fetch_archive(target: Path, url: str, sha256: str, download: Downloader) -> None:
    """Make `target` hold the archive with checksum `sha256`, or raise CorpusError (exit 4)."""
    if target.exists():
        if file_sha256(target) != sha256:
            raise CorpusError("corpus archive on disk does not match the pinned SHA-256")
        return
    partial = partial_path(target)
    if partial.exists() and file_sha256(partial) == sha256:
        # Interrupted after the last byte: resuming would ask for a range past the end (416).
        partial.replace(target)
        return
    offset = partial.stat().st_size if partial.exists() else 0
    try:
        download(url, partial, offset)
    except urllib.error.HTTPError as exc:
        if exc.code == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE:
            # The partial cannot be resumed (longer than the file, or not a prefix of it).
            partial.unlink(missing_ok=True)
        raise CorpusError("corpus download failed; rerun to resume") from exc
    except OSError as exc:
        raise CorpusError("corpus download failed; rerun to resume") from exc
    if file_sha256(partial) != sha256:
        partial.unlink()
        raise CorpusError("downloaded corpus does not match the pinned SHA-256")
    partial.replace(target)
