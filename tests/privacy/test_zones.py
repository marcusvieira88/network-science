from __future__ import annotations

import re
from pathlib import Path

import polars as pl
import pytest

from enron_case import zones
from enron_case.config import Config
from enron_case.context import StageContext
from enron_case.errors import PrivacyViolation
from enron_case.synth import SynthOutput
from enron_case.zones import Zone
from helpers import tmp_paths

SRC = Path(__file__).resolve().parents[2] / "src" / "enron_case"


@pytest.mark.parametrize(
    ("package", "zone", "mode"),
    [
        ("network", Zone.INGEST, "r"),
        ("finding", Zone.RAW, "r"),
        ("report", Zone.RESTRICTED, "r"),
        ("release", Zone.INGEST, "r"),
        ("uiexport", Zone.RESTRICTED, "r"),
        ("pseudo", Zone.INGEST, "w"),
        ("clean", Zone.RELEASE, "w"),
        ("unknown", Zone.COUNTS, "r"),
    ],
)
def test_disallowed_access_raises(package: str, zone: Zone, mode: str) -> None:
    with pytest.raises(PrivacyViolation):
        zones.check(package, zone, mode)


def test_path_cannot_escape_zone(tmp_path: Path) -> None:
    with pytest.raises(PrivacyViolation):
        zones.path_for(tmp_paths(tmp_path), "network", Zone.RESTRICTED, "../ingest/x", "r")


def test_purge_ingest_removes_zone(tmp_path: Path) -> None:
    paths = tmp_paths(tmp_path)
    target = zones.path_for(paths, "clean", Zone.INGEST, "x.parquet", "w")
    target.write_text("x")
    zones.purge_ingest(paths)
    assert not paths.dir(Zone.INGEST).exists()


def test_only_release_writes_release_tables(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = StageContext("report", Config(), tmp_paths(tmp_path), True, lambda _m: None)
    with pytest.raises(PrivacyViolation):
        ctx.write("risk", synth.table("risk"))


def test_restricted_write_rejects_addresses(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = StageContext("finding", Config(), tmp_paths(tmp_path), True, lambda _m: None)
    leaked = synth.table("metric_series").with_columns(pl.lit("a@b.com").alias("variant"))
    with pytest.raises(PrivacyViolation):
        ctx.write("metric_series", leaked)


def test_counts_reject_addresses(tmp_path: Path) -> None:
    ctx = StageContext("clean", Config(), tmp_paths(tmp_path), True, lambda _m: None)
    with pytest.raises(PrivacyViolation):
        ctx.write_counts("clean_counts", {"example": "someone@example.com"})


@pytest.mark.parametrize(
    ("zone_ref", "allowed_modules"),
    [
        (r"Zone\.RAW|\.archive\b", {"aux_public.py"}),
        (r"Zone\.INGEST|Zone\.TRUTH|read_truth|has_truth|address_map", {"score.py"}),
    ],
)
def test_risk_zone_exceptions_are_confined(zone_ref: str, allowed_modules: set[str]) -> None:
    """Only the documented risk modules may touch raw / ingest / truth."""
    for path in (SRC / "risk").rglob("*.py"):
        if path.name in allowed_modules:
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(zone_ref, text), f"risk/{path.name} references {zone_ref}"
