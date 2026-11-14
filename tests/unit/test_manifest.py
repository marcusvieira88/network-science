"""The run manifest holds no wall-clock time, so committed output stays deterministic."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from enron_case.config import SAMPLE_ARCHIVE
from enron_case.manifest import RunManifest
from enron_case.zones import Zone
from helpers import run_sample


def manifest() -> RunManifest:
    return RunManifest(parameters={"k_min": 5}, seed=1, sample=True, code_version="abc")


def test_written_manifest_has_no_wall_clock_time(tmp_path: Path) -> None:
    path = tmp_path / "run_manifest.json"
    manifest().write(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "written_utc" not in data
    assert data["code_version"] == "abc"


def test_same_manifest_writes_identical_bytes(tmp_path: Path) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    manifest().write(first)
    manifest().write(second)
    assert first.read_bytes() == second.read_bytes()


def test_manifest_records_the_hash_of_the_archive_parsed(tmp_path: Path) -> None:
    run = run_sample(tmp_path, last="parse")
    archive = run.paths.dir(Zone.RAW) / SAMPLE_ARCHIVE
    expected = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert run.result.manifest.corpus_sha256 == expected
    written = json.loads((run.paths.release_root / "run_manifest.json").read_text())
    assert written["corpus_sha256"] == expected
