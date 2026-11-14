"""The fetch stage and a sample run record the verified corpus SHA-256 for the run manifest."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from enron_case.config import CORPUS_ARCHIVE, SAMPLE_ARCHIVE, Config
from enron_case.context import StageContext
from enron_case.ingest import stage
from enron_case.synth import SynthOutput
from enron_case.zones import Zone
from helpers import run_sample, tmp_paths

PAYLOAD = b"a corpus archive"


def test_fetch_records_the_verified_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pinned = hashlib.sha256(PAYLOAD).hexdigest()
    monkeypatch.setattr(stage, "CORPUS_SHA256", pinned)
    ctx = StageContext("ingest", Config(), tmp_paths(tmp_path), sample=False)
    archive = ctx.path(Zone.RAW, CORPUS_ARCHIVE, "w")
    archive.write_bytes(PAYLOAD)
    stage.fetch(ctx)
    assert ctx.corpus_sha256 == pinned


def test_sample_run_records_the_synthetic_archive_checksum(tmp_path: Path) -> None:
    run = run_sample(tmp_path, last="parse")
    archive = run.paths.dir(Zone.RAW) / SAMPLE_ARCHIVE
    expected = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert run.result.manifest.corpus_sha256 == expected
    written = (run.paths.release_root / "run_manifest.json").read_text(encoding="utf-8")
    assert f'"corpus_sha256": "{expected}"' in written


def test_parse_records_the_hash_of_the_archive_it_read(synth: SynthOutput, tmp_path: Path) -> None:
    """A real run started at parse (`--from parse`) skips fetch; the manifest must still name the
    archive that was parsed, not stay null."""
    ctx = StageContext("ingest", Config(), tmp_paths(tmp_path), sample=False)
    archive = ctx.path(Zone.RAW, CORPUS_ARCHIVE, "w")
    shutil.copyfile(synth.archive, archive)
    stage.parse(ctx)
    assert ctx.corpus_sha256 == hashlib.sha256(archive.read_bytes()).hexdigest()
