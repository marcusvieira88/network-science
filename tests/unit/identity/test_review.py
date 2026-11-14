"""T046 manual merge review: only counts are kept."""

from __future__ import annotations

import json
from pathlib import Path

from enron_case.identity import review
from enron_case.synth import SynthOutput
from enron_case.zones import Zone
from helpers import ctx_with_fixtures


def test_review_keeps_only_counts(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("identity", synth, tmp_path, tables=("address_map",))
    answers = iter(["y", "n", "s"] + ["y"] * 100)
    shown: list[str] = []
    checked, correct = review.review(ctx, ask=lambda _p: next(answers), show=shown.append)
    merges = synth.table("address_map").drop_nulls("rule").height
    assert checked == merges - 1  # one skipped
    assert correct == checked - 1  # one judged wrong
    stored = json.loads((ctx.paths.dir(Zone.COUNTS) / "identity_manual.json").read_text())
    assert stored == {"manual_checked": checked, "manual_correct": correct}


def test_reprompts_on_unknown_answer(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("identity", synth, tmp_path, tables=("address_map",))
    answers = iter(["maybe", "y"] + ["y"] * 100)
    checked, _ = review.review(ctx, ask=lambda _p: next(answers), show=lambda _m: None)
    assert checked == synth.table("address_map").drop_nulls("rule").height
