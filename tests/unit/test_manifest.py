"""The run manifest holds no wall-clock time, so committed output stays deterministic."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from enron_case.config import SAMPLE_ARCHIVE
from enron_case.manifest import DIRTY_SUFFIX, RunManifest, code_version
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


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def _committed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "code.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "init", "--quiet")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t", "commit", "--quiet", "-m", "c")
    return repo


def test_code_version_is_the_short_commit_of_a_clean_tree(tmp_path: Path) -> None:
    repo = _committed_repo(tmp_path)
    assert code_version(repo) == _git(repo, "rev-parse", "--short", "HEAD")


def test_code_version_marks_uncommitted_source_changes(tmp_path: Path) -> None:
    repo = _committed_repo(tmp_path)
    (repo / "src" / "code.py").write_text("x = 2\n", encoding="utf-8")
    assert code_version(repo) == _git(repo, "rev-parse", "--short", "HEAD") + DIRTY_SUFFIX


def test_code_version_ignores_changed_outputs(tmp_path: Path) -> None:
    repo = _committed_repo(tmp_path)
    (repo / "release").mkdir()
    (repo / "release" / "table.csv").write_text("a\n", encoding="utf-8")
    assert code_version(repo) == _git(repo, "rev-parse", "--short", "HEAD")


def test_merged_manifest_keeps_the_code_version_of_each_stage(tmp_path: Path) -> None:
    path = tmp_path / "run_manifest.json"
    full = RunManifest(parameters={}, seed=1, sample=True, code_version="old")
    full.record_stage("parse")
    full.record_stage("finding")
    full.write(path)
    partial = RunManifest(parameters={}, seed=1, sample=True, code_version="new")
    partial.record_stage("finding")
    partial.write(path, merge=True)
    stages = json.loads(path.read_text(encoding="utf-8"))["stages"]
    versions = [(s["stage"], s["code_version"]) for s in stages]
    assert versions == [("parse", "old"), ("finding", "new")]
