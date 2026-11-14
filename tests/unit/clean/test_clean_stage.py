"""Clean stage against the synthetic reference fixture (T031)."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from enron_case.clean.stage import run
from enron_case.context import StageContext
from enron_case.contracts import schemas
from enron_case.synth import SynthOutput
from helpers import ctx_with_fixtures


@pytest.fixture
def cleaned(synth: SynthOutput, tmp_path: Path) -> StageContext:
    ctx = ctx_with_fixtures("clean", synth, tmp_path, tables=("header_records",))
    run(ctx)
    return ctx


def test_messages_equal_reference_fixture(synth: SynthOutput, cleaned: StageContext) -> None:
    out = cleaned.read("messages")
    expected = synth.table("messages")
    schemas.validate(out, "messages")
    assert out.get_column("msg_key").equals(expected.get_column("msg_key"))
    for name in out.columns[1:]:
        differs = int(out.get_column(name).ne_missing(expected.get_column(name)).sum())
        assert differs == 0, f"{name}: {differs} rows differ from the reference"
    assert out.equals(expected)


def test_counts_match_reference(synth: SynthOutput, cleaned: StageContext) -> None:
    counts = cleaned.read_counts("clean_counts")
    expected = synth.counts("clean_counts")
    for name in ("records_in", "messages_out", "removed_exact", "removed_subset", "flags"):
        assert counts[name] == expected[name], name
    assert counts["message_id_shared_share"] == pytest.approx(0.0)
    assert counts["dedupe_precision"] >= 0.95
    assert counts["dedupe_recall"] is not None


def test_counts_null_scores_without_truth(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("clean", synth, tmp_path, tables=("header_records",))
    ctx.sample = False
    run(ctx)
    counts = ctx.read_counts("clean_counts")
    assert counts["dedupe_precision"] is None
    assert counts["dedupe_recall"] is None


def test_out_of_range_dates_are_kept(synth: SynthOutput, cleaned: StageContext) -> None:
    out = cleaned.read("messages")
    flagged = out.filter(pl.col("flags").list.contains("date_out_of_range"))
    assert flagged.height > 0
    assert cleaned.read_counts("clean_counts")["flags"]["date_out_of_range"] == flagged.height


def test_logs_counts_only(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("clean", synth, tmp_path, tables=("header_records",))
    lines: list[str] = []
    ctx.log = lines.append
    run(ctx)
    assert lines
    assert not any("@" in line for line in lines)
