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

from enron_case.config import HYPOTHESES_STATED, PRIOR_WORK_YEAR, Config
from enron_case.contracts import vocab
from enron_case.errors import ContractViolation, PrivacyViolation
from enron_case.finding.exploratory import PLACEBO_FRACTION
from enron_case.report import quality, render
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
    "departures",
    "departure_tests",
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
        "## Hypotheses H1–H4 (pre-registered)",
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


def run_parameters(config: Config) -> list[float]:
    """Run parameters the H26 section states (its definitions and decision rule), and the
    year of the prior work H25 tests: a citation, the one number no release table holds."""
    return [
        float(PRIOR_WORK_YEAR),
        float(config.alpha),
        float(HYPOTHESES_STATED),
        float(config.departure_silence_weeks),
        float(config.departure_live_weeks),
        float(config.departure_active_weeks),
        float(config.departure_lookback_weeks),
        float(config.departure_rolling_min_at_risk),
    ]


def test_every_number_in_report_traces_to_a_release_cell(
    synth: SynthOutput, tmp_path: Path
) -> None:
    text = render_report(synth, tmp_path)
    numbers, dates = cell_values(synth, REPORT_TABLES)
    config = ctx_with_fixtures("report", synth, tmp_path / "cfg").config
    numbers += [float(config.k_min), float(config.seed), *run_parameters(config)]
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
    numbers += [float(ctx.config.k_min), float(ctx.config.seed), float(PRIOR_WORK_YEAR)]
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
        "The `other` row of `community_groups.csv` is not a community: it holds the 25838 "
        "internal people without a baseline group, either because they have no tie in the "
        "baseline period or because their community has fewer than 5 people. Its ties are "
        "published like a group's, but the explorer does not draw it as a group: it labels "
        "these people as outside the baseline groups and states, for each week, the share of "
        "mail that involves them."
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


# ---- contradiction review: one finding, one wording -------------------------------------------

BARE_NO_FINDING = re.compile(r"\bno finding\b", re.IGNORECASE)


def test_finding_section_states_the_record_finding_then_the_behavioural_null(
    synth: SynthOutput,
) -> None:
    """The record changed, and no behavioural finding is claimed: both, in that order."""
    record_finding = (
        "The finding: the record changed (high confidence that it changed; cause not established)."
    )
    hypotheses = _no_headline(synth, {"H2": "yes"})
    section = render.finding_section(hypotheses, _checks(synth, {"H2": False}), record_finding)
    assert section.startswith(
        f"## The finding\n\n{record_finding} No behavioural finding about the crisis year is "
        "claimed. H2 passed the pre-registered statistical tests but failed its check"
    )


def test_finding_section_without_a_record_change_opens_with_the_behavioural_statement(
    synth: SynthOutput,
) -> None:
    section = render.finding_section(_no_headline(synth, {}), _checks(synth, {}), "")
    assert section.startswith("## The finding\n\nNo hypothesis is supported.")


@pytest.mark.parametrize("name", DOCUMENTS)
def test_no_template_says_a_bare_no_finding(name: str) -> None:
    assert BARE_NO_FINDING.search(load_template(name)) is None


@pytest.mark.parametrize("fixture", ["synth", "synth_nochange"])
def test_no_generated_text_says_a_bare_no_finding(
    fixture: str, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    corpus: SynthOutput = request.getfixturevalue(fixture)
    ctx = ctx_with_fixtures("report", corpus, tmp_path, tables=RELEASE_TABLES)
    values = render.document_values(render.ReleaseTables.read(ctx), ctx.config)
    texts = [render_report(corpus, tmp_path / "report")]
    texts += [render.inject(load_template(name), values) for name in DOCUMENTS]
    texts.append(
        render.headline_statement(_no_headline(corpus, {"H2": "yes"}), _checks(corpus, {}))
    )
    for text in texts:
        assert BARE_NO_FINDING.search(text) is None


# ---- when each hypothesis was stated ----------------------------------------------------------


def _family_rows(families: dict[str, str]) -> pl.DataFrame:
    return pl.DataFrame({"hypothesis": list(families), "family": list(families.values())})


def test_timing_statement_uses_the_three_labels_from_the_family_column() -> None:
    hypotheses = pl.DataFrame({"hypothesis": ["H1", "H2", "H3", "H4"]})
    exploratory = _family_rows({"H5": "first", "H6": "first", "H7": "second", "H25": "post hoc"})
    assert render.timing_statement(hypotheses, exploratory) == (
        "H1–H4: pre-registered (before any real data was analysed); "
        "H5–H7: stated before computed, after earlier results; "
        f"H25 and H{HYPOTHESES_STATED}: post hoc (stated after every other result was known, "
        "still before its own result was computed)."
    )


def test_report_labels_every_hypothesis_table_with_its_timing(
    synth: SynthOutput, tmp_path: Path
) -> None:
    text = render_report(synth, tmp_path)
    preregistered = text.split("## Hypotheses H1–H4 (pre-registered)", 1)[1]
    assert "H5–H24: stated before computed, after earlier results" in preregistered
    exploratory = text.split("## Hypotheses H5–H25", 1)[1].split("## Privacy", 1)[0]
    assert "| ID | Stated | Measure |" in exploratory
    assert "| H5 | stated before computed, after earlier results |" in exploratory
    assert "| H25 | post hoc |" in exploratory
    assert "Frantz" not in text  # prior work is named neutrally, in one wording


# ---- placebo, leave-one-out and the results that moved the other way --------------------------


def _row(**overrides: object) -> dict[str, object]:
    """One exploratory row: predicted up, a clear rise, a flat placebo, every check passing."""
    row: dict[str, object] = {
        "hypothesis": "H9",
        "family": "first",
        "measure": "m",
        "direction": "up",
        "median_change": 0.2,
        "ci_low": 0.1,
        "ci_high": 0.3,
        "p_holm": 0.01,
        "placebo_median": 0.0,
        "placebo_ci_low": -0.1,
        "placebo_ci_high": 0.1,
        "placebo_passes": True,
        "loo_stable": True,
        "outcome": "not supported",
        "caveat": "",
        "retention_passes": None,
    }
    return {**row, **overrides}


# H21 as released: predicted up, fell; the placebo interval lies wholly below zero as well.
FELL_WITH_PLACEBO = _row(
    hypothesis="H21",
    median_change=-0.148,
    ci_low=-0.191,
    ci_high=-0.106,
    placebo_median=-0.139,
    placebo_ci_low=-0.257,
    placebo_ci_high=-0.0672,
)
# H14 as released: predicted up, fell; the placebo rose and its interval includes zero.
FELL_ALONE = _row(
    hypothesis="H14",
    median_change=-0.168,
    ci_low=-0.272,
    ci_high=-0.102,
    placebo_median=0.0816,
    placebo_ci_low=-0.0279,
    placebo_ci_high=0.105,
)


def test_placebo_shows_change_when_its_interval_lies_on_the_side_the_crisis_moved_to() -> None:
    assert render.placebo_shows_change(FELL_WITH_PLACEBO)
    assert not render.placebo_shows_change(FELL_ALONE)


def test_placebo_shows_change_when_its_median_is_at_least_as_large_on_that_side() -> None:
    """H25 as released: crisis 0.00826, placebo 0.0248 with an interval touching zero."""
    larger = _row(median_change=0.00826, placebo_median=0.0248, placebo_ci_low=0.0)
    assert render.placebo_shows_change(larger)
    smaller = _row(median_change=0.2, placebo_median=0.19, placebo_ci_low=-0.01)
    assert not render.placebo_shows_change(smaller)


def test_placebo_shows_no_change_for_a_flat_or_suppressed_comparison() -> None:
    assert not render.placebo_shows_change(_row(median_change=0.0, placebo_median=0.0))
    assert not render.placebo_shows_change(_row(placebo_median=None))


def test_exploratory_table_says_when_a_passing_placebo_already_shows_the_change() -> None:
    table = pl.DataFrame([FELL_WITH_PLACEBO, FELL_ALONE, _row(placebo_passes=False)])
    table = table.with_columns(
        pl.lit(32).alias("custodians"), pl.lit(15).alias("placebo_custodians")
    )
    section = render.exploratory_section(table)
    assert "| passes; the calm period already shows this change | stable |" in section
    assert section.count("the calm period already shows this change |") == 1
    assert "| 15 | passes | stable |" in section and "| 15 | fails | stable |" in section


def test_column_notes_state_the_placebo_and_leave_one_out_rules_as_coded() -> None:
    """The placebo rule (finding/exploratory.py `_placebo_passes`) and the leave-one-out rule
    (`_loo_stable`) in words; "half" is PLACEBO_FRACTION."""
    assert PLACEBO_FRACTION == 0.5
    notes = render.COLUMN_NOTES
    assert "no change in the predicted direction" in notes
    assert "its median lies below half the crisis median on the predicted side" in notes
    assert "A calm-period change against the prediction therefore passes" in notes
    assert "keeps the predicted sign with each custodian left out in turn" in notes
    assert "not, by itself, a statement that one person drives the result" in notes


def test_opposite_statement_names_each_result_that_moved_against_its_prediction() -> None:
    untestable = _row(hypothesis="H5", median_change=-0.44, ci_low=-0.51, ci_high=-0.37)
    untestable["caveat"] = "invalid: the hour convention changes"
    flat = _row(hypothesis="H8", median_change=0.0, ci_low=-0.02, ci_high=0.03)
    table = pl.DataFrame([untestable, flat, FELL_ALONE, FELL_WITH_PLACEBO])
    text = render.opposite_statement(table)
    assert text.startswith(
        "H14 and H21 are listed as not supported because they moved against the prediction, "
        "not because nothing moved: H14 (m, predicted up) changed by a median of -0.168 "
        "(interval -0.272 to -0.102); H21 (m, predicted up) changed by a median of -0.148 "
        "(interval -0.191 to -0.106)."
    )
    assert "H5" not in text and "H8" not in text
    assert text.endswith(
        "For H21 the pre-crisis placebo, whose windows both lie before that change, already "
        "shows the same move (-0.139 (interval -0.257 to -0.0672)), so the change of the "
        "record does not explain it."
    )
    assert "For H14" not in text


def test_opposite_statement_reads_a_predicted_fall_that_rose() -> None:
    rose = _row(hypothesis="H22", direction="down", median_change=0.0578, ci_low=0.0405)
    text = render.opposite_statement(pl.DataFrame([rose]))
    assert text.startswith("H22 is listed as not supported because it moved against")
    assert render.opposite_statement(pl.DataFrame([_row(outcome="inconclusive")])) == ""


def test_inconclusive_statement_names_the_failed_checks() -> None:
    """H20 as released: significant on the predicted side, but the placebo fails."""
    h20 = _row(
        hypothesis="H20",
        outcome="inconclusive",
        median_change=5.85,
        ci_low=5.05,
        ci_high=7.74,
        p_holm=0.0004,
        placebo_median=3.3,
        placebo_ci_low=1.6,
        placebo_ci_high=4.7,
        placebo_passes=False,
    )
    retention_only = _row(hypothesis="H16", outcome="inconclusive", retention_passes=False)
    text = render.inconclusive_statement(pl.DataFrame([h20, retention_only]))
    assert text == (
        "H20 (m) is inconclusive: it changed in the predicted direction by a median of 5.85 "
        "(interval 5.05 to 7.74), significant after Holm's correction (p = 0.0004), but its "
        "pre-crisis placebo fails (3.3 (interval 1.6 to 4.7)), so it is not held true."
    )


def test_timestamp_hypothesis_row_points_to_the_record_reading(
    synth: SynthOutput, tmp_path: Path
) -> None:
    """H5 is untestable as behaviour and is the evidence of the record finding: its row says
    which reading applies where."""
    exploratory = render_report(synth, tmp_path).split("## Hypotheses H5–H25", 1)[1]
    row = next(line for line in exploratory.splitlines() if line.startswith("| H5 |"))
    assert row.endswith(
        "Untestable as a hypothesis about behaviour; the record section reads the same "
        "estimate as a measurement of the record |"
    )


# ---- risk: only the person-level output is measured -------------------------------------------


def _risk(rates: dict[tuple[str, str], float]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "release_variant": variant,
                "attacker": attacker,
                "reid_top1": rate,
                "finding_survives": None,
            }
            for (variant, attacker), rate in rates.items()
        ],
        schema={
            "release_variant": pl.Utf8,
            "attacker": pl.Utf8,
            "reid_top1": pl.Float64,
            "finding_survives": pl.Boolean,
        },
    )


def test_risk_verdict_words_a_zero_on_an_aggregate_release_as_design_not_measurement() -> None:
    lines = render.risk_verdicts(_risk({("R0", "A1"): 0.251, ("R1", "A1"): 0.0}))
    assert lines == [
        "R1 and A1: A1 re-identified a share of 0.251 on R0 (measured). On R1 the attack does "
        "not apply: no person-level record remains for it to match, so its rate there is 0 by "
        "construction, not a measurement; the mitigation target is met in that sense only. "
        "Finding survives: —."
    ]


def test_risk_verdict_reports_a_measured_rate_against_the_mitigation_target() -> None:
    """A non-zero rate on a mitigated release is a measurement: target is half the R0 rate."""
    met = render.risk_verdicts(_risk({("R0", "A2"): 0.6, ("R1", "A2"): 0.3}))
    assert "of 0.3 on R1 (at most half: target met)" in met[0]
    missed = render.risk_verdicts(_risk({("R0", "A2"): 0.6, ("R1", "A2"): 0.31}))
    assert "of 0.31 on R1 (more than half: target missed)" in missed[0]


def test_risk_section_never_calls_the_aggregate_releases_attacked(
    synth: SynthOutput, tmp_path: Path
) -> None:
    risk = render_report(synth, tmp_path).split("## Privacy and re-identification risk", 1)[1]
    risk = risk.split("## Limits", 1)[0]
    assert "Releases attacked" not in risk and "at least halved" not in risk
    assert "both person-level attacks" not in risk
    assert "is the only release whose rows below are measurements" in risk
    assert "| R1 | A1 | 50 | 0 | 12 | 0 (by construction) |" in risk
    assert "| R0 | A1 | 50 | 0.94 | 1 | 0.9 |" in risk


def test_aggregate_risk_phrase_follows_the_published_rates() -> None:
    zero = _risk({("R0", "A1"): 0.251, ("R1", "A1"): 0.0, ("R1", "A2"): 0.0})
    assert render.aggregate_risk_phrase(zero) == (
        "The aggregate release (R1) holds no person-level record for these attacks to match: "
        "their rate there is 0 by construction, not a measurement."
    )
    measured = _risk({("R0", "A1"): 0.251, ("R1", "A1"): 0.0, ("R1", "A2"): 0.02})
    assert render.aggregate_risk_phrase(measured) == (
        "Run against the aggregate release (R1), the same attacks reach 0 and 0.02."
    )


# ---- header rulings, content wording, identity quality ----------------------------------------


def _fields(rulings: dict[str, str]) -> pl.DataFrame:
    return pl.DataFrame({"field": list(rulings), "ruling": list(rulings.values())})


def test_ruling_legend_marks_identifiers_that_are_not_retained() -> None:
    fields = _fields({"From": "identifier", "X-FileName": "identifier", "X-Origin": "identifier"})
    assert quality.ruling_legend(fields) == (
        "- **identifier**: used inside the ingest zone only, then pseudonymized or discarded; "
        "X-FileName, X-Origin: direct identifier, not retained (dropped by the parser, so it never "
        "enters the ingest zone)"
    )
    assert "not retained" not in quality.ruling_legend(_fields({"From": "identifier"}))


def test_content_ruling_uses_the_precise_wording() -> None:
    legend = quality.ruling_legend(_fields({"Subject": "content"}))
    assert "never decoded, parsed, held, stored or logged" in legend
    assert "discarded as the header is scanned" in legend
    assert "reduced at once to one of four classes and never kept" in legend
    assert len(vocab.FOLDER_CLASSES) == 4


def test_report_does_not_claim_content_is_never_read(synth: SynthOutput, tmp_path: Path) -> None:
    text = render_report(synth, tmp_path)
    assert "never read" not in text and "do not read" not in text
    assert "read out" not in text


def test_identity_quality_phrase_separates_synthetic_truth_from_the_manual_sample(
    synth: SynthOutput,
) -> None:
    assert render.identity_quality_phrase(synth.table("data_quality")) == (
        "No manual check of real merges was run; precision and recall are measured on the "
        "synthetic corpus only."
    )
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
    text = render.identity_quality_phrase(pl.concat([synth.table("data_quality"), manual]))
    assert text == (
        "A manual check of 50 sampled merges, judged by a person, found 0 wrong (precision "
        "interval 0.929 to 1); it gives no recall, and precision and recall are measured on "
        "the synthetic corpus only."
    )


def test_not_established_summary_names_artifact_and_retention_failures(
    synth: SynthOutput,
) -> None:
    hypotheses = _no_headline(synth, {"H2": "yes", "H3": "yes"})
    checks = _checks(synth, {"H2": False, "H3": False})
    exploratory = pl.DataFrame({"hypothesis": ["H16", "H17"], "retention_passes": [False, None]})
    assert render.not_established_summary(hypotheses, checks, exploratory) == (
        "H2 and H3 failed their checks against a known artifact of the data; H16 is not "
        "established once inbox retention is accounted for."
    )
    nothing = pl.DataFrame({"hypothesis": ["H16"], "retention_passes": [True]})
    assert render.not_established_summary(_no_headline(synth, {}), checks, nothing) == (
        "No apparent signal failed a check against a known artifact."
    )
