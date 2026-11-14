"""T090: the UI export reads only the release zone, has the documented shape, refuses
identifiers and small person counts, and is byte-identical for the same input."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import polars as pl
import pytest

from enron_case.config import PUBLIC_EVENTS
from enron_case.context import StageContext
from enron_case.contracts import schemas
from enron_case.contracts.counts import JsonObject, json_object
from enron_case.errors import ContractViolation, PrivacyViolation
from enron_case.release import kanon
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
        "code_version": code_version,
        "sample": True,
        "seed": ctx.config.seed,
        "parameters": ctx.config.as_record(),
        "key_fingerprint": "0" * 16,
        "corpus_sha256": None,
        "tables": {},
        "counts": {},
        "stages": [{"stage": "release", "code_version": code_version}],
    }
    path = ctx.paths.dir(Zone.RELEASE) / "run_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")


def release_ctx(synth: SynthOutput, root: Path) -> StageContext:
    ctx = ctx_with_fixtures("uiexport", synth, root, tables=RELEASE_TABLES)
    write_manifest(ctx)
    return ctx


def output(ctx: StageContext) -> JsonObject:
    return json_object(ui_file(ctx).read_text(encoding="utf-8"), "release.json")


def released(ctx: StageContext) -> dict[str, list[JsonObject]]:
    """The `tables` block of release.json: table name -> rows."""
    tables = output(ctx)["tables"]
    assert isinstance(tables, dict)
    out: dict[str, list[JsonObject]] = {}
    for name, rows in tables.items():
        assert isinstance(rows, list) and all(isinstance(row, dict) for row in rows), name
        out[name] = rows
    return out


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
    assert sorted(data) == [
        "contract_version",
        "events",
        "format_version",
        "run",
        "tables",
        "windows",
    ]
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
    tables = released(ctx)
    assert sorted(tables) == sorted(RELEASE_TABLES)
    for name in RELEASE_TABLES:
        rows = tables[name]
        expected = synth.table(name)
        assert len(rows) == expected.height, name
        names = [c.name for c in schemas.table(name).cols]
        assert all(list(row) == names for row in rows), name


def test_exploratory_windows_are_exported(synth: SynthOutput, tmp_path: Path) -> None:
    """The crisis and reference windows of docs/hypotheses-exploratory.md."""
    ctx = release_ctx(synth, tmp_path)
    run(ctx)
    assert output(ctx)["windows"] == {
        "crisis": {"start": "2001-08-14", "end": "2001-12-02"},
        "reference": {"start": "2000-08-14", "end": "2000-12-02"},
    }


def test_values_round_trip_with_nulls_and_iso_dates(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = release_ctx(synth, tmp_path)
    run(ctx)
    tables = released(ctx)
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
        "precision_ci_low": None,
        "precision_ci_high": None,
    }


def test_artifact_checks_are_exported(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = release_ctx(synth, tmp_path)
    run(ctx)
    checks = released(ctx)["artifact_checks"]
    assert [(r["hypothesis"], r["check"], r["passes"]) for r in checks] == [
        ("H2", "baseline_placebo", True),
        ("H3", "within_custodian", True),
    ]
    assert checks[1]["statistic"] == -0.05


def test_exploratory_hypotheses_are_exported(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = release_ctx(synth, tmp_path)
    run(ctx)
    rows = released(ctx)["exploratory"]
    assert [r["hypothesis"] for r in rows] == [f"H{i}" for i in range(5, 26)]
    assert not [r for r in rows if r["outcome"] == "confident"]
    h16 = next(r for r in rows if r["hypothesis"] == "H16")
    assert (h16["outcome"], h16["retention_passes"]) == ("inconclusive", False)
    h16_caveat = h16["caveat"]
    assert isinstance(h16_caveat, str) and h16_caveat.startswith("fails the retention check")
    e1 = rows[0]
    assert e1["equalised_median"] is None
    e1_caveat = e1["caveat"]
    assert isinstance(e1_caveat, str) and e1_caveat.startswith("invalid:")


def test_departure_tables_are_exported(synth: SynthOutput, tmp_path: Path) -> None:
    """H26: the fixture's two departures in each other window are below k, so their count and
    share are null; the crisis wave of twelve of forty is published."""
    ctx = release_ctx(synth, tmp_path)
    run(ctx)
    tables = released(ctx)
    periods = {row["period"]: row for row in tables["departures"]}
    assert list(periods) == list(schemas.DEPARTURE_PERIODS)
    assert periods["crisis"] == {
        "order": 1,
        "period": "crisis",
        "period_start": "2001-08-14",
        "period_end": "2001-12-02",
        "at_risk": 40,
        "departures": 12,
        "record_ends": None,
        "hazard": 0.3,
    }
    assert (periods["reference"]["departures"], periods["reference"]["hazard"]) == (None, None)
    tests = tables["departure_tests"]
    assert [(row["variant"], row["outcome"]) for row in tests] == [
        ("primary", "moderate"),
        ("silence 8", None),
    ]
    assert tests[1]["p"] is None
    assert "smallest_cell" not in tests[0]


@pytest.mark.parametrize("column", ["at_risk", "departures"])
def test_refuses_departure_count_below_k(synth: SynthOutput, tmp_path: Path, column: str) -> None:
    ctx = release_ctx(synth, tmp_path)
    df = synth.table("departures").with_columns(pl.lit(ctx.config.k_min - 1).alias(column))
    replace_table(ctx, "departures", df)
    with pytest.raises(PrivacyViolation):
        run(ctx)


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


def test_refuses_active_persons_value_below_k(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = release_ctx(synth, tmp_path)
    df = synth.table("weekly_metrics")
    first_active = (pl.col("metric") == "active_persons") & (
        pl.col("metric") == "active_persons"
    ).cum_sum().eq(1)
    df = df.with_columns(
        pl.when(first_active)
        .then(float(ctx.config.k_min - 1))
        .otherwise(pl.col("value"))
        .alias("value")
    )
    assert df.filter(pl.col("metric") == "active_persons").height
    replace_table(ctx, "weekly_metrics", df)
    with pytest.raises(PrivacyViolation):
        run(ctx)


def test_person_count_columns_have_one_source() -> None:
    assert export.check_person_counts.__module__ == "enron_case.uiexport.export"
    assert not hasattr(export, "PERSON_COUNT_COLUMNS")
    assert not hasattr(kanon, "PERSON_COUNT_COLUMNS")
    assert schemas.PERSON_COUNT_COLUMNS["weekly_metrics"] == ("n_active",)
    assert schemas.PERSON_COUNT_METRIC == "active_persons"


def test_person_count_equal_to_k_is_published(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = release_ctx(synth, tmp_path)
    df = synth.table("community_groups").with_columns(pl.lit(ctx.config.k_min).alias("n_persons"))
    replace_table(ctx, "community_groups", df)
    run(ctx)
    sizes = {r["n_persons"] for r in released(ctx)["community_groups"]}
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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_number_is_exported_as_null(
    synth: SynthOutput, tmp_path: Path, value: float
) -> None:
    ctx = release_ctx(synth, tmp_path)
    df = synth.table("hypotheses").with_columns(pl.lit(value).alias("null_z"))
    replace_table(ctx, "hypotheses", df)
    run(ctx)
    rows = released(ctx)["hypotheses"]
    assert [row["null_z"] for row in rows] == [None] * df.height
    assert "NaN" not in ui_file(ctx).read_text(encoding="utf-8")


def test_jsonable_maps_non_finite_to_none() -> None:
    assert export.table_rows(pl.DataFrame({"x": [1.5, float("nan"), float("-inf")]})) == [
        {"x": 1.5},
        {"x": None},
        {"x": None},
    ]


CONTEXT_BYTES = 120


def test_committed_ui_sample_matches_release_fixtures(synth: SynthOutput, tmp_path: Path) -> None:
    """The UI's bundled sample is this export of the release fixtures. Regenerate it with
    UPDATE_UI_SAMPLE=1 uv run pytest tests/unit/uiexport -k committed_ui_sample."""
    ctx = release_ctx(synth, tmp_path)
    run(ctx)
    produced = ui_file(ctx).read_bytes()
    if os.environ.get("UPDATE_UI_SAMPLE") == "1":
        UI_SAMPLE.write_bytes(produced)
    committed = UI_SAMPLE.read_bytes()
    assert committed == produced, _first_difference(committed, produced)


def _first_difference(committed: bytes, produced: bytes) -> str:
    """Where the two files part, with context, so a platform difference is visible in CI."""
    index = next(
        (i for i, (a, b) in enumerate(zip(committed, produced, strict=False)) if a != b),
        min(len(committed), len(produced)),
    )
    start = max(index - CONTEXT_BYTES, 0)
    end = index + CONTEXT_BYTES
    return (
        f"first difference at byte {index}: committed {committed[start:end]!r} "
        f"produced {produced[start:end]!r}"
    )


def test_run_block_names_the_missing_manifest_fields() -> None:
    with pytest.raises(
        ContractViolation, match=r"run manifest lacks \['code_version', 'parameters'\]"
    ):
        export.run_block({"seed": 1, "sample": True})


def test_run_block_keeps_only_the_run_fields_in_contract_order() -> None:
    manifest: JsonObject = {
        "parameters": {},
        "seed": 1,
        "extra": "x",
        "sample": True,
        "code_version": "c",
    }
    assert list(export.run_block(manifest).items()) == [
        ("code_version", "c"),
        ("sample", True),
        ("seed", 1),
        ("parameters", {}),
    ]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_render_refuses_a_non_finite_number(value: float) -> None:
    """Table cells are nulled before this point; a non-finite number anywhere else (a run
    parameter, say) would make invalid JSON, so it fails instead."""
    with pytest.raises(ContractViolation, match="non-finite number"):
        export.render({"run": {"parameters": {"alpha": value}}})


def test_render_is_compact_json_with_a_final_newline() -> None:
    assert export.render({"b": 1, "a": [1.5, None]}) == '{"b":1,"a":[1.5,null]}\n'
