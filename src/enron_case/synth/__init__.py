"""Synthetic corpus, ground truth and contract fixtures.

out = generate(Path("data/sample"))       # archive in raw/, truth in truth/, fixtures/
out.table("messages")                      # reference answer for the clean stage
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

from enron_case.config import SAMPLE_ARCHIVE
from enron_case.contracts import schemas
from enron_case.synth.archive import build_files, write_archive
from enron_case.synth.fixtures import FixtureBuilder
from enron_case.synth.model import SynthSpec, build_organisation, generate_messages

__all__ = ["SynthOutput", "SynthSpec", "generate"]


@dataclass(frozen=True)
class SynthOutput:
    root: Path

    @property
    def archive(self) -> Path:
        return self.root / "raw" / SAMPLE_ARCHIVE

    @property
    def truth_path(self) -> Path:
        return self.root / "truth" / "truth.json"

    @property
    def fixtures(self) -> Path:
        return self.root / "fixtures"

    def truth(self) -> dict[str, Any]:
        data: dict[str, Any] = json.loads(self.truth_path.read_text(encoding="utf-8"))
        return data

    def table(self, name: str) -> pl.DataFrame:
        spec = schemas.table(name)
        path = self.fixtures / spec.filename
        if spec.fmt == "csv":
            return pl.read_csv(path, schema=spec.polars_schema)
        return pl.read_parquet(path)

    def counts(self, name: str) -> dict[str, Any]:
        data: dict[str, Any] = json.loads(
            (self.fixtures / "counts" / f"{name}.json").read_text(encoding="utf-8")
        )
        return data


def generate(root: Path, spec: SynthSpec | None = None) -> SynthOutput:
    """Write the synthetic archive, its ground truth and every contract fixture under `root`."""
    spec = spec or SynthSpec()
    rng = random.Random(spec.seed)
    org = build_organisation(spec, rng)
    messages = generate_messages(spec, org, rng)
    files = build_files(org, messages, rng)
    out = SynthOutput(root)
    write_archive(files, out.archive)

    builder = FixtureBuilder(spec, org, messages, files)
    out.truth_path.parent.mkdir(parents=True, exist_ok=True)
    out.truth_path.write_text(
        json.dumps(builder.truth(), indent=1, sort_keys=True), encoding="utf-8"
    )

    (out.fixtures / "counts").mkdir(parents=True, exist_ok=True)
    for name, df in builder.all_tables().items():
        schemas.validate(df, name)
        target = out.fixtures / schemas.table(name).filename
        if schemas.table(name).fmt == "csv":
            df.write_csv(target)
        else:
            df.write_parquet(target)
    for name, counts in builder.counts().items():
        (out.fixtures / "counts" / f"{name}.json").write_text(
            json.dumps(counts, indent=2, sort_keys=True), encoding="utf-8"
        )
    return out
