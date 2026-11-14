"""Content never enters the system (Principle I, SC-001).

Runs every implemented stage on the synthetic corpus, which carries canary markers in bodies,
subjects, folder names and file names, then scans every artifact and log.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from enron_case.synth import SynthOutput
from enron_case.zones import Zone
from helpers import SampleRun, run_sample, scan

CONTENT_MARKERS = ["CANARYBODY", "CANARYSUBJ", "CANARYFOLDER", "CANARYFILE"]


@pytest.fixture(scope="module")
def sample_run(tmp_path_factory: pytest.TempPathFactory) -> SampleRun:
    return run_sample(tmp_path_factory.mktemp("canary"), keep_ingest=True)


def _strings(value: object) -> list[str]:
    assert isinstance(value, list) and all(isinstance(v, str) for v in value)
    return [str(v) for v in value]


def identifiers(truth: dict[str, object]) -> list[str]:
    return ["@", *_strings(truth["display_names"]), *_strings(truth["owner_dirs"])]


def test_pipeline_ran_something(sample_run: SampleRun) -> None:
    if not sample_run.result.ran:
        pytest.skip("no stage implemented yet")


def test_no_content_marker_anywhere(sample_run: SampleRun) -> None:
    """Content markers appear in no zone at all, the ingest zone included, nor in logs."""
    paths = sample_run.paths
    for zone in (Zone.INGEST, Zone.RESTRICTED, Zone.RELEASE, Zone.UI, Zone.DOCS):
        assert scan(paths.dir(zone), CONTENT_MARKERS) == {}, zone
    assert not any(m.lower() in line.lower() for line in sample_run.logs for m in CONTENT_MARKERS)


def test_no_identifier_past_the_boundary(sample_run: SampleRun, synth: SynthOutput) -> None:
    needles = identifiers(synth.truth())
    paths = sample_run.paths
    for zone in (Zone.RESTRICTED, Zone.RELEASE, Zone.UI, Zone.DOCS):
        assert scan(paths.dir(zone), needles) == {}, zone
    manifest = paths.dir(Zone.RELEASE) / "run_manifest.json"
    if manifest.exists():
        text = manifest.read_text(encoding="utf-8")
        assert not any(n.lower() in text.lower() for n in needles)


def test_logs_carry_no_identifier(sample_run: SampleRun, synth: SynthOutput) -> None:
    needles = [n.lower() for n in identifiers(synth.truth())]
    for line in sample_run.logs:
        assert not any(n in line.lower() for n in needles), "identifier in log line"


def test_scanner_finds_planted_marker(tmp_path: Path) -> None:
    (tmp_path / "x.json").write_text(json.dumps({"a": "zzCANARYBODYzz"}))
    assert scan(tmp_path, CONTENT_MARKERS) == {"x.json": 1}
