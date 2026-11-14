"""StageContext: the only way a stage reads and writes data.

Every read and write goes through the zone guard; every table write is conformed, validated
against its contract, checked for identifier leaks and fingerprinted. Stages never build paths
into data directories themselves.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

from enron_case import zones
from enron_case.config import CORPUS_ARCHIVE, SAMPLE_ARCHIVE, Config
from enron_case.contracts import schemas
from enron_case.errors import ContractViolation, PrivacyViolation
from enron_case.manifest import fingerprint, fingerprint_json
from enron_case.zones import Paths, Zone

LogFn = Callable[[str], None]


def stderr_log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


@dataclass
class StageContext:
    """Per-stage handle. `package` decides which zones are reachable."""

    package: str
    config: Config
    paths: Paths
    sample: bool
    log: LogFn = stderr_log
    outputs: dict[str, str] = field(default_factory=dict)
    count_outputs: dict[str, str] = field(default_factory=dict)
    # Set by the fetch stage once the archive matches its pinned checksum (run manifest).
    corpus_sha256: str | None = None

    # ---- tables -------------------------------------------------------------------------
    def read(self, name: str) -> pl.DataFrame:
        spec = schemas.table(name)
        path = zones.path_for(self.paths, self.package, spec.zone, spec.filename, "r")
        if not path.exists():
            raise ContractViolation(f"input table '{name}' has not been produced")
        if spec.fmt == "csv":
            return pl.read_csv(path, schema=spec.polars_schema)
        return pl.read_parquet(path)

    def write(self, name: str, df: pl.DataFrame) -> pl.DataFrame:
        """Conform, validate, leak-check and write a contract table. Returns what was written."""
        spec = schemas.table(name)
        if spec.zone is Zone.RELEASE and self.package != "release":
            raise PrivacyViolation("only the release package writes release tables")
        out = schemas.conform(df, name)
        schemas.validate(out, name)
        self._leak_check(out, spec.zone, name)
        path = zones.path_for(self.paths, self.package, spec.zone, spec.filename, "w")
        if spec.fmt == "csv":
            out.write_csv(path)
        else:
            out.write_parquet(path)
        self.outputs[name] = fingerprint(out)
        return out

    def _leak_check(self, df: pl.DataFrame, zone: Zone, name: str) -> None:
        if zone is Zone.RESTRICTED:
            hits = schemas.leak_count(df, (r"@",))
        elif zone is Zone.RELEASE:
            hits = schemas.leak_count(df)
        else:
            return
        if hits:
            raise PrivacyViolation(f"{name}: {hits} identifier-shaped values in zone {zone.value}")

    # ---- counts side outputs (counts only; readable by release and report) ---------------
    def write_counts(self, name: str, counts: dict[str, Any]) -> None:
        text = json.dumps(counts, indent=2, sort_keys=True, default=str)
        if "@" in text:
            raise PrivacyViolation(f"counts '{name}' contain an address")
        path = zones.path_for(self.paths, self.package, Zone.COUNTS, f"{name}.json", "w")
        path.write_text(text + "\n", encoding="utf-8")
        self.count_outputs[name] = fingerprint_json(counts)

    def read_counts(self, name: str) -> dict[str, Any]:
        """A counts side output; a missing one is an error naming it, never an empty mapping."""
        counts = self.read_optional_counts(name)
        if counts is None:
            raise ContractViolation(f"counts '{name}' have not been produced; run its stage first")
        return counts

    def read_optional_counts(self, name: str) -> dict[str, Any] | None:
        """A counts side output that only some runs produce (the manual merge review), or None.
        On real runs a committed copy in the checks zone is used when this run has none, so a
        fresh clone publishes the same release."""
        path = zones.path_for(self.paths, self.package, Zone.COUNTS, f"{name}.json", "r")
        if not path.exists() and not self.sample:
            path = zones.path_for(self.paths, self.package, Zone.CHECKS, f"{name}.json", "r")
        if not path.exists():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def write_check(self, name: str, counts: dict[str, Any]) -> None:
        """Commit-safe copy of a check a person made (counts only) in the checks zone."""
        text = json.dumps(counts, indent=2, sort_keys=True, default=str)
        if "@" in text:
            raise PrivacyViolation(f"check '{name}' contains an address")
        path = zones.path_for(self.paths, self.package, Zone.CHECKS, f"{name}.json", "w")
        path.write_text(text + "\n", encoding="utf-8")

    # ---- other files ------------------------------------------------------------------------
    def path(self, zone: Zone, name: str, mode: str) -> Path:
        """Guarded path for non-table files (archive, report.md, release.json)."""
        return zones.path_for(self.paths, self.package, zone, name, mode)

    def has_truth(self) -> bool:
        return self.sample and (self.paths.dir(Zone.TRUTH) / "truth.json").exists()

    def read_truth(self) -> dict[str, Any]:
        """Synthetic ground truth. Only exists for the sample corpus."""
        path = zones.path_for(self.paths, self.package, Zone.TRUTH, "truth.json", "r")
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    @property
    def archive(self) -> Path:
        name = SAMPLE_ARCHIVE if self.sample else CORPUS_ARCHIVE
        return self.path(Zone.RAW, name, "r")
