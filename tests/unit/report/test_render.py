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

from enron_case.contracts import vocab
from enron_case.errors import ContractViolation, PrivacyViolation
from enron_case.report import render
from enron_case.report.stage import DOCUMENTS, run
from enron_case.report.templates import load_template
from enron_case.synth import SynthOutput
from enron_case.zones import Zone
from helpers import ctx_with_fixtures

REPORT_TABLES = (
    "data_quality",
    "header_fields",
    "hypotheses",
    "risk",
    "artifact_checks",
    "exploratory",
    "record_profile",
    "community_groups",
)
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


def test_quality_section_shows_the_funnel_detail(synth: SynthOutput, tmp_path: Path) -> None:
    quality = render_report(synth, tmp_path).split("## The finding", 1)[0]
    for step in (
        "deduplicate: exact copies",
        "deduplicate: subset copies",
        "flag: bad address",
        "flag: self-only",
        "events in the network",
    ):
        assert f"| {step} |" in quality, step
    assert "files, messages or events, not persons" in quality
    assert "addresses" in quality.split("mass mailing", 1)[1]  # the flag's unit is stated


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


def test_stage_refuses_a_document_with_an_identifier(
    synth: SynthOutput, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Documents are scanned like the report: an address-shaped or pseudonym-shaped string in a
    template or an injected value stops the run before anything is written."""
    leaky = "k = {{k_min}}; contact " + "someone" + "@" + "example.org"
    monkeypatch.setattr("enron_case.report.stage.load_template", lambda _name: leaky)
    ctx = dataclasses.replace(
        ctx_with_fixtures("report", synth, tmp_path, tables=RELEASE_TABLES), sample=False
    )
    with pytest.raises(PrivacyViolation):
        run(ctx)
    assert not any(ctx.paths.dir(Zone.DOCS).glob("*.md"))


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


def test_release_descriptions_do_not_overclaim() -> None:
    assert "re-keyed" not in render.RELEASE_VARIANTS["R1"]
    assert "no pseudonyms" in render.RELEASE_VARIANTS["R1"]
    r2 = render.RELEASE_VARIANTS["R2"]
    assert "not calibrated" in r2
    assert "calibrated noise" not in r2


def test_limits_name_the_optimistic_interval_and_the_n2_risk(
    synth: SynthOutput, tmp_path: Path
) -> None:
    text = render_report(synth, tmp_path)
    limits = text.split("## Limits", 1)[1]
    assert "change week chosen from the same data" in limits
    assert "optimistic" in limits
    assert "regional subdomains" in limits
    assert "no manual check of merges was run" in limits  # the fixture has no manual step


def _groups(rows: list[tuple[str, int]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema={"group": pl.Utf8, "n_persons": pl.Int64}, orient="row")


def test_outside_statement_says_what_the_other_bucket_is_and_its_size() -> None:
    groups = _groups([("G01", 926), ("G02", 743), (vocab.OTHER_GROUP, 25838)])
    text = render.outside_statement(groups, k_min=5)
    assert text == (
        "The `other` row of `community_groups.csv` is not a community: it holds the 25838 people "
        "with no tie in the baseline period (such as people first seen after it) "
        "plus any community of fewer than 5 people. Its ties are published like a group's, but "
        "the explorer does not draw it as a group: it labels these people as outside the "
        "baseline groups and states, for each week, the share of mail that involves them."
    )


def test_outside_statement_without_the_bucket_says_it_is_withheld() -> None:
    text = render.outside_statement(_groups([("G01", 926)]), k_min=5)
    assert text == (
        "No `other` row is published in `community_groups.csv`: fewer than 5 people fall outside "
        "the groups, so none is shown."
    )


def test_limits_section_explains_the_other_bucket(synth: SynthOutput, tmp_path: Path) -> None:
    limits = render_report(synth, tmp_path).split("## Limits", 1)[1]
    assert "No `other` row is published" in limits  # the synthetic fixture has no bucket


def test_n2_limit_reports_the_manual_check_from_data_quality(synth: SynthOutput) -> None:
    manual = pl.DataFrame(
        {
            "order": [4, 5],
            "step": ["manual merge check", "manual merge check: rule N2"],
            "count_in": [50, 12],
            "count_out": [49, 11],
            "removed": [1, 1],
            "rule": ["seeded sample, judged by a person"] * 2,
            "precision": [0.98, 11 / 12],
            "recall": [None, None],
            "precision_ci_low": [0.894, 0.615],
            "precision_ci_high": [0.9995, 0.998],
        },
        schema=synth.table("data_quality").schema,
    )
    quality = pl.concat([synth.table("data_quality"), manual])
    text = " ".join(render.limits(quality, synth.table("community_groups"), 5))
    assert (
        "a manual check of 50 real merges, sampled from the merges of every rule, found 1 wrong"
        in text
    )
    assert "precision 0.98, exact binomial interval 0.894 to 1" in text
    assert "rule N2 accounts for 12 of the sampled merges and 1 of the wrong ones" in text


def test_funnel_table_shows_the_precision_interval(synth: SynthOutput, tmp_path: Path) -> None:
    quality = render_report(synth, tmp_path).split("## The finding", 1)[0]
    assert "| Precision low | Precision high |" in quality


def test_held_true_statement_gives_the_family_adjusted_equalised_p(synth: SynthOutput) -> None:
    exploratory = synth.table("exploratory").with_columns(
        pl.when(pl.col("hypothesis") == "H20")
        .then(pl.lit("confident"))
        .otherwise(pl.col("outcome"))
        .alias("outcome")
    )
    text = render.exploratory_statement(exploratory)
    assert "Held true: H20" in text
    assert "family-adjusted p = 0.02" in text


def test_risk_section_says_why_utility_is_empty_without_headline(
    synth_nochange: SynthOutput, tmp_path: Path
) -> None:
    risk = render_report(synth_nochange, tmp_path).split("## Privacy and re-identification", 1)[1]
    assert "no headline finding to recompute" in risk
    assert "H5–H25 are computed in the finding stage on restricted data" in risk


def test_risk_section_has_no_empty_utility_note_with_headline(
    synth: SynthOutput, tmp_path: Path
) -> None:
    risk = render_report(synth, tmp_path).split("## Privacy and re-identification", 1)[1]
    assert "no headline finding to recompute" not in risk


def test_report_states_the_weaker_placebo(synth: SynthOutput, tmp_path: Path) -> None:
    text = render_report(synth, tmp_path)
    exploratory = text.split("## Hypotheses H5–H25", 1)[1].split("## Privacy", 1)[0]
    assert "| Placebo custodians |" in exploratory
    assert "| 32 | 0.25 | 0.12 to 0.38 | 0.002 | 15 |" in exploratory  # H16: crisis n, placebo n
    limits = text.split("## Limits", 1)[1]
    assert "placebos run on fewer custodians than the crisis comparison" in limits
    assert "does not exclude a pre-existing trend" in limits


def _retention_row(hypothesis: str, placebo_passes: bool, loo_stable: bool) -> dict[str, object]:
    return {
        "hypothesis": hypothesis,
        "measure": "m",
        "outcome": "inconclusive",
        "median_change": 1.0,
        "ci_low": 0.5,
        "ci_high": 1.5,
        "caveat": "fails the retention check",
        "placebo_passes": placebo_passes,
        "loo_stable": loo_stable,
        "retention_passes": False,
        "retention_median": 0.1,
        "retention_ci_low": -0.1,
        "retention_ci_high": 0.3,
    }


def test_only_a_row_that_met_its_rule_is_called_so() -> None:
    # H16 passed its placebo and leave-one-out checks and failed only the retention check;
    # H17 also failed its placebo, so it never met its stated rule.
    table = pl.DataFrame([_retention_row("H16", True, True), _retention_row("H17", False, True)])
    text = render.exploratory_statement(table)
    assert "H16 (m) met its stated rule" in text
    assert "H17" not in text
    # An interval spanning zero shows the change is not established, not that retention
    # explains it.
    assert "largely explained" not in text


def test_retention_sentence_does_not_claim_retention_is_held_fixed() -> None:
    table = pl.DataFrame([_retention_row("H16", True, True)])
    text = render.exploratory_statement(table)
    assert "held fixed" not in text
    assert "depends less on what one inbox kept" in text


def test_n2_limit_without_a_per_rule_count_says_the_rule_mix_is_not_recorded(
    synth: SynthOutput,
) -> None:
    manual = pl.DataFrame(
        {
            "order": [4],
            "step": ["manual merge check"],
            "count_in": [50],
            "count_out": [50],
            "removed": [0],
            "rule": ["seeded sample, judged by a person"],
            "precision": [1.0],
            "recall": [None],
            "precision_ci_low": [0.929],
            "precision_ci_high": [1.0],
        },
        schema=synth.table("data_quality").schema,
    )
    text = " ".join(
        render.limits(
            pl.concat([synth.table("data_quality"), manual]), synth.table("community_groups"), 5
        )
    )
    assert "sampled from the merges of every rule" in text
    assert "how many were N2 merges is not in the committed check" in text
