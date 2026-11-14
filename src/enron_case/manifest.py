"""Content fingerprints and the run manifest.

Fingerprints hash a canonical row serialisation, not Parquet bytes, so identical content gives
identical fingerprints across library versions. The manifest holds no key and no identifier.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

import enron_case


def fingerprint(df: pl.DataFrame) -> str:
    """SHA-256 of the table's canonical NDJSON serialisation (rows already in contract order)."""
    return hashlib.sha256(df.write_ndjson().encode("utf-8")).hexdigest()


def fingerprint_json(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def code_version(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return enron_case.__version__


@dataclass
class RunManifest:
    parameters: dict[str, Any]
    seed: int
    sample: bool
    code_version: str
    key_fingerprint: str | None = None
    corpus_sha256: str | None = None
    tables: dict[str, str] = field(default_factory=dict)
    counts: dict[str, str] = field(default_factory=dict)
    stages: list[dict[str, Any]] = field(default_factory=list)

    def record_stage(self, name: str, seconds: float) -> None:
        self.stages.append({"stage": name, "seconds": round(seconds, 2)})

    def analytical_fingerprints(self) -> dict[str, str]:
        """Fingerprints that must match across runs with the same inputs and key."""
        return dict(sorted({**self.tables, **self.counts}.items()))

    def write(self, path: Path) -> None:
        payload = {
            "written_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
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


def read_manifest(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data
