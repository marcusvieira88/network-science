"""T090: the UI export reads only the release zone, has the documented shape, refuses
identifiers and small person counts, and is byte-identical for the same input."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from enron_case.config import PUBLIC_EVENTS
from enron_case.context import StageContext
from enron_case.contracts import schemas
from enron_case.errors import ContractViolation, PrivacyViolation
from enron_case.synth import SynthOutput
from enron_case.uiexport import export
from enron_case.uiexport.stage import run
from enron_case.zones import Zone
from helpers import ctx_with_fixtures

RELEASE_TABLES = export.RELEASE_TABLES
UI_SAMPLE = Path(__file__).resolve().parents[3] / "ui" / "public" / "data" / "release.sample.json"
FIXTURE_CODE_VERSION = "fixture"


def write_manifest(ctx: StageContext, code_version: str = FIXTURE_CODE_VERSION) -> None:
    """A run manifest as the orchestrator writes it, including fields the export must drop."""
    manifest = {
        "written_utc": "2026-11-14T12:00:00Z",
        "code_version": code_version,
        "sample": True,
        "seed": ctx.config.seed,
        "parameters": ctx.config.as_record(),
        "key_fingerprint": "0" * 16,
        "corpus_sha256": None,
        "tables": {},
        "counts": {},
        "stages": [{"stage": "release", "seconds": 1.23}],
    }
    path = ctx.paths.dir(Zone.RELEASE) / "run_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")


def release_ctx(synth: SynthOutput, root: Path) -> StageContext:
    ctx = ctx_with_fixtures("uiexport", synth, root, tables=RELEASE_TABLES)
    write_manifest(ctx)
    return ctx


def output(ctx: StageContext) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(ui_file(ctx).read_text(encoding="utf-8"))
    return data


def ui_file(ctx: StageContext) -> Path:
    return ctx.paths.dir(Zone.UI) / "release.json"


def replace_table(ctx: StageContext, name: str, df: pl.DataFrame) -> None:
    spec = schemas.table(name)
    df.write_csv(ctx.paths.dir(Zone.RELEASE) / spec.filename)


def test_reads_only_the_release_zone(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = release_ctx(synth, tmp_path)
    shutil.rmtree(ctx.paths.data_root)  # raw, ingest, restricted, counts, truth all gone
    run(ctx)
    assert ui_file(ctx).exists()


def test_other_packages_cannot_write_the_ui_file(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = release_ctx(synth, tmp_path)
    ctx.package = "release"
    with pytest.raises(PrivacyViolation):
        run(ctx)


def test_shape_matches_documented_layout(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = release_ctx(synth, tmp_path)
    run(ctx)
    data = output(ctx)
    assert sorted(data) == ["contract_version", "events", "format_version", "run", "tables"]
    assert data["format_version"] == export.FORMAT_VERSION
    assert data["contract_version"] == schemas.CONTRACT_VERSION
    assert data["run"] == {
        "code_version": FIXTURE_CODE_VERSION,
        "sample": True,
        "seed": ctx.config.seed,
        "parameters": ctx.config.as_record(),
    }
    assert data["events"] == [
        {"date": day.isoformat(), "label": label} for day, label in PUBLIC_EVENTS
    ]
    assert sorted(data["tables"]) == sorted(RELEASE_TABLES)
    for name in RELEASE_TABLES:
        rows = data["tables"][name]
        expected = synth.table(name)
        assert len(rows) == expected.height, name
        names = [c.name for c in schemas.table(name).cols]
        assert all(list(row) == names for row in rows), name


def test_values_round_trip_with_nulls_and_iso_dates(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = release_ctx(synth, tmp_path)
    run(ctx)
    tables = output(ctx)["tables"]
    h1 = tables["hypotheses"][0]
    assert h1["hypothesis"] == "H1"
    assert h1["change_week"] == "2001-08-13"
    assert h1["is_headline"] is True
    assert h1["effect"] == 1.8
    h3 = tables["hypotheses"][2]
    assert h3["change_week"] is None
    suppressed = [r for r in tables["degree_distribution"] if r["degree_bucket"] == "10+"]
    assert suppressed and all(r["persons"] is None for r in suppressed)
    first_dq = tables["data_quality"][0]
    assert first_dq == {
        "order": 1,
        "step": "files parsed",
        "count_in": 6731,
        "count_out": 6731,
        "removed": 0,
        "rule": None,
        "precision": None,
        "recall": None,
    }


def test_artifact_checks_are_exported(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = release_ctx(synth, tmp_path)
    run(ctx)
    checks = output(ctx)["tables"]["artifact_checks"]
    assert [(r["hypothesis"], r["check"], r["passes"]) for r in checks] == [
        ("H2", "baseline_placebo", True),
        ("H3", "within_custodian", True),
    ]
    assert checks[1]["statistic"] == -0.05


def test_same_input_gives_byte_identical_json(synth: SynthOutput, tmp_path: Path) -> None:
    first = release_ctx(synth, tmp_path / "a")
    second = release_ctx(synth, tmp_path / "b")
    run(first)
    run(second)
    assert ui_file(first).read_bytes() == ui_file(second).read_bytes()


@pytest.mark.parametrize(
    "value",
    ["someone@example.com", "p_abcdefghijklmnop", "o_abcdefghijklmnop", "x p_abcdefghijklmnop"],
)
def test_refuses_identifier_shaped_values(synth: SynthOutput, tmp_path: Path, value: str) -> None:
    ctx = release_ctx(synth, tmp_path)
    df = synth.table("header_fields")
    df = df.with_columns(
        pl.when(pl.int_range(pl.len()) == 0).then(pl.lit(value)).otherwise("ruling").alias("ruling")
    )
    replace_table(ctx, "header_fields", df)
    with pytest.raises(PrivacyViolation) as info:
        run(ctx)
    assert info.value.exit_code == 6
    assert value not in str(info.value)
    assert not ui_file(ctx).exists()


def test_refuses_identifier_in_parameters(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = release_ctx(synth, tmp_path)
    path = ctx.paths.dir(Zone.RELEASE) / "run_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["parameters"]["internal_domain"] = "someone@example.com"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(PrivacyViolation):
        run(ctx)


@pytest.mark.parametrize(
    ("name", "column"),
    [
        ("community_groups", "n_persons"),
        ("degree_distribution", "persons"),
        ("weekly_metrics", "n_active"),
        ("risk", "n_targets"),
    ],
)
def test_refuses_person_count_below_k(
    synth: SynthOutput, tmp_path: Path, name: str, column: str
) -> None:
    ctx = release_ctx(synth, tmp_path)
    df = synth.table(name)
    small = ctx.config.k_min - 1
    df = df.with_columns(
        pl.when(pl.int_range(pl.len()) == 0).then(small).otherwise(pl.col(column)).alias(column)
    )
    replace_table(ctx, name, df)
    with pytest.raises(PrivacyViolation) as info:
        run(ctx)
    assert info.value.exit_code == 6


def test_person_count_equal_to_k_is_published(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = release_ctx(synth, tmp_path)
    df = synth.table("community_groups").with_columns(pl.lit(ctx.config.k_min).alias("n_persons"))
    replace_table(ctx, "community_groups", df)
    run(ctx)
    sizes = {r["n_persons"] for r in output(ctx)["tables"]["community_groups"]}
    assert sizes == {ctx.config.k_min}


def test_missing_table_is_a_contract_violation(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = release_ctx(synth, tmp_path)
    (ctx.paths.dir(Zone.RELEASE) / "risk.csv").unlink()
    with pytest.raises(ContractViolation):
        run(ctx)


def test_missing_manifest_is_a_contract_violation(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = release_ctx(synth, tmp_path)
    (ctx.paths.dir(Zone.RELEASE) / "run_manifest.json").unlink()
    with pytest.raises(ContractViolation):
        run(ctx)


def test_non_finite_number_is_a_contract_violation(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = release_ctx(synth, tmp_path)
    df = synth.table("risk").with_columns(pl.lit(float("inf")).alias("reid_top1"))
    replace_table(ctx, "risk", df)
    with pytest.raises(ContractViolation):
        run(ctx)


def test_committed_ui_sample_matches_release_fixtures(synth: SynthOutput, tmp_path: Path) -> None:
    """The UI's bundled sample is this export of the release fixtures. Regenerate it with
    UPDATE_UI_SAMPLE=1 uv run pytest tests/unit/uiexport -k committed_ui_sample."""
    ctx = release_ctx(synth, tmp_path)
    run(ctx)
    produced = ui_file(ctx).read_bytes()
    if os.environ.get("UPDATE_UI_SAMPLE") == "1":
        UI_SAMPLE.write_bytes(produced)
    assert UI_SAMPLE.read_bytes() == produced
