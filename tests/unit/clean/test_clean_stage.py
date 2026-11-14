"""Clean stage against the synthetic reference fixture (T031)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from enron_case.clean.dedupe import Group, exact_pass, subset_pass
from enron_case.clean.stage import clean_counts, messages_frame, run
from enron_case.config import Config
from enron_case.context import StageContext
from enron_case.contracts import schemas
from enron_case.release.tables import require_mapping, require_rate
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
    precision = require_rate(counts, "clean_counts", "dedupe_precision")
    assert precision is not None
    assert precision >= 0.95
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
    flags = require_mapping(cleaned.read_counts("clean_counts"), "clean_counts", "flags")
    assert flags["date_out_of_range"] == flagged.height


def test_logs_counts_only(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("clean", synth, tmp_path, tables=("header_records",))
    lines: list[str] = []
    ctx.log = lines.append
    run(ctx)
    assert lines
    assert not any("@" in line for line in lines)


def _copy(file_id: str, recipients: dict[str, str]) -> Group:
    return Group.single(
        file_id=file_id,
        owner="o",
        folder_class="inbox",
        sender="a@x.org",
        ts_utc=datetime(2001, 5, 14, 9, 0, tzinfo=UTC),
        recipients=recipients,
        message_id=None,
        bad_address=False,
    )


def test_removed_copies_are_counted_per_pass() -> None:
    # Five identical copies (exact pass removes 4) and one Cc-less copy that the subset pass
    # folds in (removes 1). The message's final rule is "subset", but only 1 copy went that way.
    full = {"b@x.org": "to", "c@x.org": "cc"}
    copies = [_copy(f"f{i}", full) for i in range(5)] + [_copy("f5", {"b@x.org": "to"})]
    exact = exact_pass(copies)
    messages = messages_frame(subset_pass(exact), Config())
    counts = clean_counts(len(copies), len(exact), messages, None, None, None)
    assert messages.get_column("dedupe_rule").to_list() == ["subset"]
    assert (counts["removed_exact"], counts["removed_subset"]) == (4, 1)
    assert counts["messages_out"] == 1
