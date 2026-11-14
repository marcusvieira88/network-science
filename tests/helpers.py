"""Shared test helpers: contexts, sample runs and leak scanning."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from enron_case.cli import RunResult, run_pipeline, select
from enron_case.config import SAMPLE_KEY_HEX, Config
from enron_case.context import StageContext
from enron_case.contracts import schemas
from enron_case.synth import SynthOutput
from enron_case.zones import Paths, Zone

TEST_KEY_HEX = SAMPLE_KEY_HEX


def tmp_paths(root: Path) -> Paths:
    return Paths(root / "data", root / "release", root / "ui", root / "docs")


def ctx_with_fixtures(
    package: str, synth: SynthOutput, root: Path, tables: tuple[str, ...] = ()
) -> StageContext:
    """A sample-mode StageContext whose zones already hold the named fixture tables,
    the synthetic archive, the ground truth and the fixture counts."""
    paths = tmp_paths(root)
    for name in tables:
        spec = schemas.table(name)
        target = paths.dir(spec.zone) / spec.filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((synth.fixtures / spec.filename).read_bytes())
    for zone, src in ((Zone.RAW, synth.archive), (Zone.TRUTH, synth.truth_path)):
        target = paths.dir(zone) / src.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(src.read_bytes())
    counts_dir = paths.dir(Zone.COUNTS)
    counts_dir.mkdir(parents=True, exist_ok=True)
    for src in (synth.fixtures / "counts").glob("*.json"):
        (counts_dir / src.name).write_bytes(src.read_bytes())
    return StageContext(
        package, Config(internal_domain="acme-energy.com"), paths, True, lambda _m: None
    )


@dataclass
class SampleRun:
    paths: Paths
    result: RunResult
    logs: list[str] = field(default_factory=list)


def run_sample(root: Path, keep_ingest: bool = False, last: str | None = None) -> SampleRun:
    """Run the pipeline (to `last`, default the report) on the synthetic sample into `root`."""
    paths = tmp_paths(root)
    logs: list[str] = []
    result = run_pipeline(
        paths,
        Config(internal_domain="acme-energy.com"),
        sample=True,
        stages=select(None, last),
        keep_ingest=keep_ingest,
        log=logs.append,
    )
    return SampleRun(paths, result, logs)


def scan(root: Path, needles: list[str]) -> dict[str, int]:
    """Count case-insensitive matches of any needle per file under `root` (Parquet cells,
    CSV/JSON/Markdown text). Returns {relative path: hits} for files with hits."""
    if not needles or not root.exists():
        return {}
    pattern = "(?i)" + "|".join(re.escape(n) for n in needles)
    hits: dict[str, int] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.suffix == ".parquet":
            n = _parquet_hits(pl.read_parquet(path), pattern)
        elif path.suffix in {".gz", ".tar"}:
            continue
        else:
            n = len(re.findall(pattern, path.read_text(encoding="utf-8", errors="replace")))
        if n:
            hits[str(path.relative_to(root))] = n
    return hits


def _parquet_hits(df: pl.DataFrame, pattern: str) -> int:
    total = 0
    for name, dtype in df.schema.items():
        col = df.get_column(name)
        if dtype == pl.List(pl.Utf8):
            col = col.explode()
        elif isinstance(dtype, pl.List) and isinstance(dtype.inner, pl.Struct):
            col = col.explode().struct.field("addr")
        if col.dtype == pl.Utf8:
            total += int(col.drop_nulls().str.contains(pattern).sum())
    return total
