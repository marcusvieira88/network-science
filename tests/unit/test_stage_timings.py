"""Stage timings change on every run, so they live in the git-ignored logs zone, never in the
committed run manifest: two identical runs write a byte-identical manifest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from enron_case.config import MANIFEST_FILE, STAGE_TIMINGS_FILE
from enron_case.manifest import RunManifest, write_stage_timings
from enron_case.zones import Zone
from helpers import run_sample


def test_manifest_stages_carry_the_code_version_and_no_duration(tmp_path: Path) -> None:
    path = tmp_path / MANIFEST_FILE
    manifest = RunManifest(parameters={}, seed=1, sample=True, code_version="abc")
    manifest.record_stage("parse")
    manifest.write(path)
    stages = json.loads(path.read_text(encoding="utf-8"))["stages"]
    assert stages == [{"stage": "parse", "code_version": "abc"}]


@pytest.mark.slow
def test_two_identical_sample_runs_write_identical_manifests(tmp_path: Path) -> None:
    first = run_sample(tmp_path / "first")
    second = run_sample(tmp_path / "second")
    written = [run.paths.dir(Zone.RELEASE) / MANIFEST_FILE for run in (first, second)]
    assert written[0].read_bytes() == written[1].read_bytes()
    timings = json.loads((first.paths.dir(Zone.LOGS) / STAGE_TIMINGS_FILE).read_text())
    assert [entry["stage"] for entry in timings["stages"]] == first.result.ran
    assert all(entry["seconds"] >= 0 for entry in timings["stages"])


def test_a_partial_run_drops_durations_a_previous_manifest_held(tmp_path: Path) -> None:
    path = tmp_path / MANIFEST_FILE
    previous = {"stages": [{"stage": "parse", "seconds": 1.23, "code_version": "old"}]}
    path.write_text(json.dumps(previous), encoding="utf-8")
    partial = RunManifest(parameters={}, seed=1, sample=True, code_version="new")
    partial.record_stage("finding")
    partial.write(path, merge=True)
    stages = json.loads(path.read_text(encoding="utf-8"))["stages"]
    assert stages == [
        {"stage": "parse", "code_version": "old"},
        {"stage": "finding", "code_version": "new"},
    ]


def test_a_partial_run_keeps_the_timings_of_stages_it_did_not_run(tmp_path: Path) -> None:
    path = tmp_path / STAGE_TIMINGS_FILE
    write_stage_timings(path, {"parse": 2.0, "report": 1.0})
    write_stage_timings(path, {"report": 3.0, "ui-data": 0.5}, merge=True)
    stages = json.loads(path.read_text(encoding="utf-8"))["stages"]
    assert stages == [
        {"stage": "parse", "seconds": 2.0},
        {"stage": "report", "seconds": 3.0},
        {"stage": "ui-data", "seconds": 0.5},
    ]
    write_stage_timings(path, {"fetch": 1.0})
    assert json.loads(path.read_text(encoding="utf-8"))["stages"] == [
        {"stage": "fetch", "seconds": 1.0}
    ]
