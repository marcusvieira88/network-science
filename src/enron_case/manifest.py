"""Content fingerprints and the run manifest.

Fingerprints hash a canonical row serialisation, not Parquet bytes, so identical content gives
identical fingerprints across library versions. The manifest holds no key, no identifier, no
wall-clock time and no duration (committed output must not change between identical runs); stage
durations go to a git-ignored run log instead (`write_stage_timings`).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

import enron_case
from enron_case.config import CODE_PATHS
from enron_case.contracts.counts import JsonObject, json_object
from enron_case.errors import ContractViolation

# Appended to the commit when source differs from it: that commit alone cannot reproduce the run.
DIRTY_SUFFIX = "-dirty"


def fingerprint(df: pl.DataFrame) -> str:
    """SHA-256 of the table's canonical NDJSON serialisation (rows already in contract order)."""
    return hashlib.sha256(df.write_ndjson().encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    """SHA-256 of a file's bytes, read in chunks (the corpus archive is about 440 MB)."""
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def fingerprint_json(payload: object) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def code_version(repo_root: Path) -> str:
    """The short commit, with DIRTY_SUFFIX when code under CODE_PATHS differs from it."""
    try:
        commit = _git(repo_root, "rev-parse", "--short", "HEAD")
        changed = _git(repo_root, "status", "--porcelain", "--", *CODE_PATHS)
    except (OSError, subprocess.CalledProcessError):
        return enron_case.__version__
    return commit + DIRTY_SUFFIX if changed else commit


@dataclass
class RunManifest:
    parameters: JsonObject
    seed: int
    sample: bool
    code_version: str
    key_fingerprint: str | None = None
    corpus_sha256: str | None = None
    tables: dict[str, str] = field(default_factory=dict)
    counts: dict[str, str] = field(default_factory=dict)
    stages: list[JsonObject] = field(default_factory=list)

    def record_stage(self, name: str) -> None:
        self.stages.append(_stage_record(name, self.code_version))

    def analytical_fingerprints(self) -> dict[str, str]:
        """Fingerprints that must match across runs with the same inputs and key."""
        return dict(sorted({**self.tables, **self.counts}.items()))

    def write(self, path: Path, merge: bool = False) -> None:
        """Write the manifest. With `merge`, a partial run updates an existing manifest:
        fingerprints of the tables it rewrote and the records of the stages it ran. Each stage
        keeps the code version that ran it; the top-level version is the latest run's."""
        if merge and path.exists():
            previous = read_manifest(path)
            self.tables = {**_string_map(previous, "tables"), **self.tables}
            self.counts = {**_string_map(previous, "counts"), **self.counts}
            ran = {s["stage"] for s in self.stages}
            kept = [
                _stage_record(_text(s, "stage"), _text(s, "code_version"))
                for s in _objects(previous, "stages")
                if s["stage"] not in ran
            ]
            self.stages = kept + self.stages
            self.key_fingerprint = self.key_fingerprint or _optional_string(
                previous, "key_fingerprint"
            )
            self.corpus_sha256 = self.corpus_sha256 or _optional_string(previous, "corpus_sha256")
        payload = {
            "code_version": self.code_version,
            "sample": self.sample,
            "seed": self.seed,
            "parameters": self.parameters,
            "key_fingerprint": self.key_fingerprint,
            "corpus_sha256": self.corpus_sha256,
            "tables": dict(sorted(self.tables.items())),
            "counts": dict(sorted(self.counts.items())),
            "stages": self.stages,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_stage_timings(path: Path, seconds: dict[str, float], merge: bool = False) -> None:
    """Write the seconds each stage of this run took to the run log. With `merge`, a partial
    run keeps the previous timings of the stages it did not run, as the manifest keeps their
    records: those come first, then this run's stages in run order."""
    stages: list[JsonObject] = []
    if merge and path.exists():
        stages = [s for s in _previous_timings(path) if s["stage"] not in seconds]
    stages += [{"stage": name, "seconds": round(value, 2)} for name, value in seconds.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"stages": stages}, indent=2) + "\n", encoding="utf-8")


def _previous_timings(path: Path) -> list[JsonObject]:
    """The stage timings an earlier run wrote, each checked to be a stage name and its seconds."""
    previous = json_object(path.read_text(encoding="utf-8"), "stage timings")
    entries = previous.get("stages", [])
    if not isinstance(entries, list):
        raise ContractViolation("stage timings: 'stages' is not a list")
    timings: list[JsonObject] = []
    for entry in entries:
        stage = entry.get("stage") if isinstance(entry, dict) else None
        value = entry.get("seconds") if isinstance(entry, dict) else None
        if not isinstance(stage, str) or not isinstance(value, int | float):
            raise ContractViolation("stage timings: an entry is not a stage name and its seconds")
        timings.append({"stage": stage, "seconds": value})
    return timings


def _stage_record(name: str, version: str) -> JsonObject:
    """A stage in the manifest: its name and the code version that ran it, nothing that varies."""
    return {"stage": name, "code_version": version}


def read_manifest(path: Path) -> JsonObject:
    return json_object(path.read_text(encoding="utf-8"), "run manifest")


def _string_map(manifest: JsonObject, key: str) -> dict[str, str]:
    """A name -> fingerprint block of a previous manifest; absent means empty."""
    value = manifest.get(key, {})
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise ContractViolation(f"run manifest: '{key}' is not a mapping of strings")
    return value


def _objects(manifest: JsonObject, key: str) -> list[JsonObject]:
    """A list-of-objects block of a previous manifest; absent means empty."""
    value = manifest.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ContractViolation(f"run manifest: '{key}' is not a list of objects")
    return value


def _text(record: JsonObject, key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str):
        raise ContractViolation(f"run manifest: a stage's '{key}' is not a string")
    return value


def _optional_string(manifest: JsonObject, key: str) -> str | None:
    value = manifest.get(key)
    if value is not None and not isinstance(value, str):
        raise ContractViolation(f"run manifest: '{key}' is not a string")
    return value
