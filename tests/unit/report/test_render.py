"""T078: the report and the documents render from release fixtures, and every number traces.

Known answers come from the release fixtures emitted by the synthetic generator
(`data_quality.csv`, `hypotheses.csv`, `risk.csv`), read here independently of the renderer.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from enron_case.errors import ContractViolation, PrivacyViolation
from enron_case.report import render
from enron_case.report.stage import DOCUMENTS, run
from enron_case.report.templates import load_template
from enron_case.synth import SynthOutput
from enron_case.zones import Zone
from helpers import ctx_with_fixtures

REPORT_TABLES = ("data_quality", "header_fields", "hypotheses", "risk", "artifact_checks")
RELEASE_TABLES = (*REPORT_TABLES, "weekly_metrics")

DATE_TOKEN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# A number not glued to a letter, digit, underscore or dot: skips H1, R0, A1, G01, p_holm.
NUMBER_TOKEN = re.compile(r"(?<![A-Za-z0-9_.])-?\d+(?:\.\d+)?(?![A-Za-z0-9_])")
PLACEHOLDER_TOKEN = re.compile(r"\{\{[a-z0-9_]+\}\}")


def render_report(synth: SynthOutput, tmp_path: Path) -> str:
    ctx = ctx_with_fixtures("report", synth, tmp_path, tables=RELEASE_TABLES)
    run(ctx)
    return ctx.path(Zone.RELEASE, "report.md", "r").read_text(encoding="utf-8")


def cell_values(synth: SynthOutput, names: tuple[str, ...]) -> tuple[list[float], set[str]]:
    """Every numeric cell and every date cell of the named fixture tables."""
    numbers: list[float] = []
    dates: set[str] = set()
    for name in names:
        df = synth.table(name)
        for column, dtype in df.schema.items():
            values = df.get_column(column).drop_nulls().to_list()
            if dtype.is_numeric():
                numbers.extend(float(v) for v in values)
            elif dtype == pl.Date:
                dates.update(v.isoformat() for v in values)
    return numbers, dates


def traces(token: str, numbers: list[float]) -> bool:
    """True if some cell rounds to the token at the token's displayed precision."""
    decimals = len(token.split(".")[1]) if "." in token else 0
    tolerance = 0.5 * 10**-decimals + 1e-12
    value = float(token)
    return any(abs(cell - value) <= tolerance for cell in numbers)


def untraced(text: str, numbers: list[float], dates: set[str]) -> list[str]:
    bad = [d for d in DATE_TOKEN.findall(text) if d not in dates]
    without_dates = DATE_TOKEN.sub(" ", text)
    bad += [t for t in NUMBER_TOKEN.findall(without_dates) if not traces(t, numbers)]
    return bad


# ---- report -------------------------------------------------------------------------------


def test_report_renders_known_values(synth: SynthOutput, tmp_path: Path) -> None:
    text = render_report(synth, tmp_path)
    quality = synth.table("data_quality").row(by_predicate=pl.col("step") == "deduplicate")
    assert str(quality[4]) in text  # duplicates removed, as an integer
    headline = synth.table("hypotheses").filter(pl.col("is_headline")).row(0, named=True)
    assert f"{headline['hypothesis']} is supported" in text
    assert "effect of 1.8" in text
    assert "1.2 to 2.4" in text
    risk = synth.table("risk").filter(
        (pl.col("release_variant") == "R0") & (pl.col("attacker") == "A1")
    )
    assert risk.get_column("reid_top1").item() == 0.9
    assert "| R0 | A1 | 50 | 0.94 | 1 | 0.9 |" in text


def test_report_has_every_section(synth: SynthOutput, tmp_path: Path) -> None:
    text = render_report(synth, tmp_path)
    for heading in (
        "## What we found in the data",
        "## The finding",
        "## All hypotheses",
        "## Privacy and re-identification risk",
        "## Limits",
    ):
        assert heading in text, heading
    for hypothesis in ("H1", "H2", "H3", "H4"):
        assert f"| {hypothesis} |" in text
    for field in ("Subject", "X-Folder", "From"):
        assert f"| {field} |" in text


def test_limits_section_has_at_least_three_items(synth: SynthOutput, tmp_path: Path) -> None:
    text = render_report(synth, tmp_path)
    limits = text.split("## Limits", 1)[1]
    assert len(re.findall(r"^- ", limits, flags=re.MULTILINE)) >= 3


def test_every_number_in_report_traces_to_a_release_cell(
    synth: SynthOutput, tmp_path: Path
) -> None:
    text = render_report(synth, tmp_path)
    numbers, dates = cell_values(synth, REPORT_TABLES)
    config = ctx_with_fixtures("report", synth, tmp_path / "cfg").config
    numbers += [float(config.k_min), float(config.seed)]
    assert untraced(text, numbers, dates) == []


def test_report_without_headline_says_none_supported(
    synth_nochange: SynthOutput, tmp_path: Path
) -> None:
    text = render_report(synth_nochange, tmp_path)
    assert "No hypothesis is supported" in text
    assert "## Limits" in text


def test_report_fails_on_missing_release_table(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("report", synth, tmp_path, tables=("data_quality", "header_fields"))
    with pytest.raises(ContractViolation):
        run(ctx)


def test_report_refuses_pseudonym_shaped_text() -> None:
    with pytest.raises(PrivacyViolation):
        render.check_no_identifiers("leaked p_abcdefghijklmnop here")


def test_report_contains_no_identifier_or_content_header_value(
    synth: SynthOutput, tmp_path: Path
) -> None:
    text = render_report(synth, tmp_path)
    assert "@" not in text
    assert not re.search(r"[po]_[a-z2-7]{16}", text)


def test_report_is_deterministic(synth: SynthOutput, tmp_path: Path) -> None:
    assert render_report(synth, tmp_path / "a") == render_report(synth, tmp_path / "b")


# ---- number injection ---------------------------------------------------------------------


def test_inject_replaces_placeholders() -> None:
    assert render.inject("removed {{a}} of {{b}}", {"a": "3", "b": "7"}) == "removed 3 of 7"


def test_inject_fails_on_unknown_placeholder() -> None:
    with pytest.raises(render.UnfilledPlaceholder, match="missing_one"):
        render.inject("value {{missing_one}}", {"a": "1"})


def test_inject_fails_on_malformed_placeholder() -> None:
    with pytest.raises(render.UnfilledPlaceholder):
        render.inject("value {{ a }}", {"a": "1"})


def test_document_values_hold_known_answers(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("report", synth, tmp_path, tables=RELEASE_TABLES)
    values = render.document_values(render.ReleaseTables.read(ctx), ctx.config)
    assert values["dq_deduplicate_removed"] == "4010"
    assert values["dq_resolve_identities_precision"] == "1"
    assert values["risk_r0_a1_reid_top1"] == "0.9"
    assert values["risk_r1_a1_reid_top1"] == "0"
    assert values["h3_supported"] == "no"
    assert values["headline_hypothesis"] == "H1"
    assert values["headline_change_week"] == date(2001, 8, 13).isoformat()
    assert values["fields_content"] == "Subject, X-Folder"
    assert values["k_min"] == str(ctx.config.k_min)


def test_headline_values_absent_without_headline(
    synth_nochange: SynthOutput, tmp_path: Path
) -> None:
    ctx = ctx_with_fixtures("report", synth_nochange, tmp_path, tables=RELEASE_TABLES)
    values = render.document_values(render.ReleaseTables.read(ctx), ctx.config)
    assert "headline_effect" not in values
    assert "No hypothesis is supported" in values["headline_statement"]


# ---- documents ----------------------------------------------------------------------------


@pytest.mark.parametrize("name", DOCUMENTS)
@pytest.mark.parametrize("fixture", ["synth", "synth_nochange"])
def test_documents_fill_every_placeholder(
    name: str, fixture: str, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    corpus: SynthOutput = request.getfixturevalue(fixture)
    ctx = ctx_with_fixtures("report", corpus, tmp_path, tables=RELEASE_TABLES)
    values = render.document_values(render.ReleaseTables.read(ctx), ctx.config)
    text = render.inject(load_template(name), values)
    assert "{{" not in text and "}}" not in text


@pytest.mark.parametrize("name", ["decision-record.md", "slides.md"])
def test_templates_type_no_number_by_hand(name: str) -> None:
    template = PLACEHOLDER_TOKEN.sub(" ", load_template(name))
    assert DATE_TOKEN.findall(template) == []
    assert NUMBER_TOKEN.findall(template) == []


def test_slides_have_at_most_twelve_slides() -> None:
    body = load_template("slides.md").split("---\n", 2)[2]  # drop Marp front matter
    slides = [s for s in re.split(r"^---$", body, flags=re.MULTILINE) if s.strip()]
    assert 1 <= len(slides) <= 12


def test_decision_record_fits_one_page(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("report", synth, tmp_path, tables=RELEASE_TABLES)
    values = render.document_values(render.ReleaseTables.read(ctx), ctx.config)
    text = render.inject(load_template("decision-record.md"), values)
    prose = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    assert len(prose.split()) <= 700


def test_documents_numbers_trace_to_release_cells(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("report", synth, tmp_path, tables=RELEASE_TABLES)
    values = render.document_values(render.ReleaseTables.read(ctx), ctx.config)
    numbers, dates = cell_values(synth, RELEASE_TABLES)
    numbers += [float(ctx.config.k_min), float(ctx.config.seed)]
    for name in ("decision-record.md", "slides.md"):
        assert untraced(render.inject(load_template(name), values), numbers, dates) == [], name


def test_stage_writes_documents_only_on_real_runs(synth: SynthOutput, tmp_path: Path) -> None:
    sample_ctx = ctx_with_fixtures("report", synth, tmp_path / "s", tables=RELEASE_TABLES)
    run(sample_ctx)
    assert not any(sample_ctx.paths.dir(Zone.DOCS).glob("*.md"))

    real_ctx = dataclasses.replace(
        ctx_with_fixtures("report", synth, tmp_path / "r", tables=RELEASE_TABLES), sample=False
    )
    run(real_ctx)
    for name in DOCUMENTS:
        text = (real_ctx.paths.dir(Zone.DOCS) / name).read_text(encoding="utf-8")
        assert "{{" not in text


# ---- review-2 wording ---------------------------------------------------------------------


def test_risk_section_says_aggregate_releases_were_not_attacked_at_person_level(
    synth: SynthOutput, tmp_path: Path
) -> None:
    text = render_report(synth, tmp_path)
    risk = text.split("## Privacy and re-identification risk", 1)[1].split("## Limits", 1)[0]
    assert "measured by attacking" not in risk
    assert "R1 and R2 hold no person-level records" in risk
    assert "return no guesses by construction" in risk
    limits = text.split("## Limits", 1)[1]
    assert "No group-level attack on the community graph was run" in limits


def _no_headline(synth: SynthOutput, supported: dict[str, str]) -> pl.DataFrame:
    return synth.table("hypotheses").with_columns(
        pl.lit(False).alias("is_headline"),
        pl.col("hypothesis").replace_strict(supported, default="no").alias("supported"),
        pl.lit("low").alias("confidence"),
    )


def _checks(synth: SynthOutput, passes: dict[str, bool | None]) -> pl.DataFrame:
    return synth.table("artifact_checks").with_columns(
        pl.col("hypothesis")
        .replace_strict(passes, return_dtype=pl.Boolean, default=None)
        .alias("passes")
    )


def test_headline_statement_never_says_an_unsupported_hypothesis_passed(
    synth: SynthOutput,
) -> None:
    hypotheses = _no_headline(synth, {})
    text = render.headline_statement(hypotheses, _checks(synth, {"H2": False, "H3": False}))
    assert "passed" not in text
    assert "H2" not in text and "H3" not in text
    assert "No hypothesis is supported" in text


def test_headline_statement_names_supported_hypotheses_with_failed_or_unrun_checks(
    synth: SynthOutput,
) -> None:
    hypotheses = _no_headline(synth, {"H2": "yes", "H3": "yes"})
    text = render.headline_statement(hypotheses, _checks(synth, {"H2": False, "H3": None}))
    assert "H2 passed the pre-registered statistical tests but failed its check" in text
    assert "H3 passed the pre-registered statistical tests but its check" in text
    assert "could not run" in text
    assert "H1" not in text and "H4" not in text


def test_headline_statement_ignores_unsupported_hypothesis_with_failed_check(
    synth: SynthOutput,
) -> None:
    hypotheses = _no_headline(synth, {"H3": "yes"})
    text = render.headline_statement(hypotheses, _checks(synth, {"H2": False, "H3": False}))
    assert "H3 passed" in text
    assert "H2" not in text


def test_confidence_words_match_the_rule_in_docs_hypotheses() -> None:
    assert "exactly one" in render.CONFIDENCE_WORDS["moderate"]
    assert "two or more" in render.CONFIDENCE_WORDS["low"]
