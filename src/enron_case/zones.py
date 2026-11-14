"""Data zones and the path guard that makes the privacy boundary checkable.

Zone 0 raw        archive (git-ignored)
Zone 1 ingest     identifiers allowed; purged at end of run
Zone 2 restricted pseudonyms only (git-ignored)
       counts     counts-only side outputs of every stage (restricted)
       truth      synthetic ground truth; exists only for the sample corpus
Zone 3 release    aggregates meeting the minimum group size (committed)
       ui         explorer UI data file, built from release only
       checks     committed counts of checks a person made (manual merge review)
       docs       documents with injected numbers, built from release only
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from enron_case.errors import PrivacyViolation


class Zone(StrEnum):
    RAW = "raw"
    INGEST = "ingest"
    RESTRICTED = "restricted"
    COUNTS = "counts"
    TRUTH = "truth"
    RELEASE = "release"
    UI = "ui"
    DOCS = "docs"
    CHECKS = "checks"


R, RW = "r", "rw"

# package -> zone -> allowed mode. Anything not listed is denied.
ALLOWED: dict[str, dict[Zone, str]] = {
    "ingest": {Zone.RAW: RW, Zone.INGEST: RW, Zone.COUNTS: RW},
    "clean": {Zone.INGEST: RW, Zone.COUNTS: RW, Zone.TRUTH: R},
    "identity": {Zone.INGEST: RW, Zone.COUNTS: RW, Zone.TRUTH: R, Zone.CHECKS: RW},
    "pseudo": {Zone.INGEST: R, Zone.RESTRICTED: RW, Zone.COUNTS: RW},
    "network": {Zone.RESTRICTED: RW, Zone.COUNTS: RW},
    "finding": {Zone.RESTRICTED: RW, Zone.COUNTS: RW},
    # Documented exceptions: only risk/aux_public.py may read RAW (the attacker's own copy
    # of the public corpus) and only risk/score.py may read INGEST and TRUTH (scoring guesses
    # against the truth, emitting counts only). Enforced by tests/privacy/test_zones.py.
    "risk": {Zone.RESTRICTED: RW, Zone.COUNTS: RW, Zone.RAW: R, Zone.INGEST: R, Zone.TRUTH: R},
    "release": {Zone.RESTRICTED: R, Zone.COUNTS: R, Zone.RELEASE: RW, Zone.CHECKS: R},
    "report": {Zone.RELEASE: RW, Zone.DOCS: RW},
    "uiexport": {Zone.RELEASE: R, Zone.UI: RW},
    # The orchestrator purges the ingest zone and writes the run manifest.
    "cli": {Zone.INGEST: RW, Zone.RELEASE: RW, Zone.RAW: RW, Zone.TRUTH: RW},
}

RISK_RAW_MODULES = ("enron_case.risk.aux_public",)
RISK_TRUTH_MODULES = ("enron_case.risk.score",)


@dataclass(frozen=True)
class Paths:
    """Filesystem layout of one run. `data_root` holds raw, ingest, restricted and truth."""

    data_root: Path
    release_root: Path
    ui_root: Path
    docs_root: Path

    @classmethod
    def for_run(cls, repo_root: Path, sample: bool) -> Paths:
        if sample:
            return cls(
                data_root=repo_root / "data" / "sample",
                release_root=repo_root / "release-sample",
                ui_root=repo_root / "ui" / "public" / "data",
                docs_root=repo_root / "release-sample" / "docs",
            )
        return cls(
            data_root=repo_root / "data",
            release_root=repo_root / "release",
            ui_root=repo_root / "ui" / "public" / "data",
            docs_root=repo_root / "docs",
        )

    def dir(self, zone: Zone) -> Path:
        if zone is Zone.RELEASE:
            return self.release_root
        if zone is Zone.UI:
            return self.ui_root
        if zone is Zone.DOCS:
            return self.docs_root
        if zone is Zone.COUNTS:
            return self.data_root / "restricted" / "counts"
        if zone is Zone.CHECKS:
            # Committed results of checks a person made (counts only), next to the release, so
            # a fresh clone reproduces them; never used by sample runs.
            return self.release_root.parent / "checks"
        return self.data_root / zone.value


def check(package: str, zone: Zone, mode: str) -> None:
    """Raise PrivacyViolation unless `package` may access `zone` in `mode` ("r" or "w")."""
    allowed = ALLOWED.get(package, {}).get(zone)
    if allowed is None or (mode == "w" and allowed != RW):
        raise PrivacyViolation(f"package '{package}' may not {mode} zone '{zone.value}'")


def path_for(paths: Paths, package: str, zone: Zone, name: str, mode: str) -> Path:
    """Guarded path of a file in a zone. Creates the zone directory for writes."""
    check(package, zone, mode)
    directory = paths.dir(zone)
    if mode == "w":
        directory.mkdir(parents=True, exist_ok=True)
    target = (directory / name).resolve()
    if directory.resolve() not in target.parents:
        raise PrivacyViolation(f"path escapes zone '{zone.value}'")
    return target


def purge_ingest(paths: Paths) -> None:
    """Delete the ingest zone: identifiers do not outlive the run. A zone that cannot be
    deleted is an error, never a silent leftover."""
    directory = paths.dir(Zone.INGEST)
    if not directory.exists():
        return
    try:
        shutil.rmtree(directory)
    except OSError as exc:
        raise PrivacyViolation("the ingest zone could not be purged; delete it by hand") from exc
