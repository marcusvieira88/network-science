"""Render `release/report.md` from release tables, and inject release numbers into documents.

Every number shown comes from a release table cell or a run parameter, formatted by
`markdown.format_value`. The placeholder -> value table for documents is `document_values`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

import polars as pl

from enron_case.config import Config
from enron_case.context import StageContext
from enron_case.contracts import schemas, vocab
from enron_case.contracts.vocab import DEFAULT_VARIANT
from enron_case.errors import ContractViolation, PrivacyViolation
from enron_case.release.tables import STEP_MANUAL, STEP_MANUAL_RULE
from enron_case.report import quality, record
from enron_case.report.markdown import bullets, format_value, table

PLACEHOLDER = re.compile(r"\{\{([a-z0-9_]+)\}\}")
IDENTIFIER = re.compile("|".join(f"(?:{p})" for p in vocab.LEAK_PATTERNS))
NO_CHECK = "no check"  # a hypothesis without an artifact check (docs/hypotheses.md)
MITIGATION_TARGET = 0.5  # SC-007: a mitigated release should at least halve the rate
STEP_MANUAL_N2 = STEP_MANUAL_RULE.format(rule="N2")

HYPOTHESIS_CLAIMS = {
    "H1": "communication concentrated on fewer people as the crisis approached",
    "H2": "communication increasingly crossed established group boundaries",
    "H3": "the organization turned inward",
    "H4": "working relationships were rewired faster",
}
CONFIDENCE_WORDS = {
    "high": "high: the change is supported and passes all three robustness checks",
    "moderate": "moderate: the change is supported but exactly one of the three robustness "
    "checks (null model, leave-one-mailbox-out, sensitivity variants) fails",
    "low": "low: the change is not supported, two or more robustness checks fail, or its check "
    "against a known artifact failed or could not run",
}
RELEASE_VARIANTS = {
    "R0": "pseudonymized person-level weekly edge list (the naive output; never published)",
    "R1": "aggregates only, every cell meeting the minimum group size, bucketed degrees, "
    "weekly resolution; it contains no pseudonyms, and groups carry size-ordered labels",
    "R2": "R1 plus seeded Laplace noise of a fixed scale on degree counts and group tie weights; "
    "the noise is not calibrated to any privacy budget (a sketch, not differential privacy)",
}
ATTACKERS = {
    "A1": "outsider who holds the public corpus and matches per-address activity features",
    "A2": "insider who knows a few true identities and propagates from them through the graph",
    "A3": "the same propagation seeded with every custodian: the public corpus names every "
    "mailbox owner, so anyone holding it knows them all",
}
ALTERNATIVE_EXPLANATIONS = (
    "Retention: what each person kept, and what was collected, differs by person and period, "
    "so coverage changes toward late in the period for reasons unrelated to behaviour.",
    "Volume: more messages alone can move a structural metric; the rewiring null model, which "
    "keeps every sender's and recipient's volume, separates the two.",
    "Sample: the collected mailboxes are mostly senior staff, and the collection was shaped by "
    "an investigation; leaving out each mailbox in turn tests whether one of them drives it.",
    "Cleaning choices: the recipient cap and the window length change the network; the "
    "sensitivity variants re-estimate the effect under each.",
)
FALSIFIERS = (
    "The effect disappears when any single mailbox is left out.",
    "The effect is no larger than the rewiring null model gives with the same volumes.",
    "The effect changes sign or loses significance under a different recipient cap or window.",
    "The same change appears at another time of the record with no comparable event.",
)
LIMITS = (
    "Coverage: the corpus holds a limited set of mailboxes, mostly senior staff. A tie is visible "
    "only when one end is a collected mailbox, so results describe this sample, not the whole "
    "organization.",
    "Retention and selection: what people kept and what was collected differ by person and "
    "period, and the collection was shaped by an investigation.",
    "Headers only: subjects are content and are excluded, so there are no threads and no reply "
    "times. Deduplication cannot use content and merges distinct messages from one sender to the "
    "same recipients in the same second.",
    "Identity resolution is rule-based and favours precision; aliases it misses split one person "
    "into several nodes.",
    "Pseudonymization is not anonymization: person-level pseudonymized data must be treated as "
    "re-identifiable (see the attack on R0), so only aggregates are published; the noise variant "
    "is a sketch, not a formal privacy budget.",
    "Observational design: a structural change near public events does not show what people "
    "knew. Hypotheses fixed in advance limit hindsight bias but do not remove it.",
    "No group-level attack on the community graph was run: an attacker who knows some group "
    "members could try to infer ties or membership from group-to-group weights, and that risk "
    "is bounded only by the minimum of k distinct senders per published tie, not measured.",
    "The effect interval is computed at a change week chosen from the same data (the week that "
    "maximises the change statistic), so it is optimistic: it ignores the uncertainty of where "
    "the change happened.",
    "For H5–H25, the pre-crisis placebos run on fewer custodians than the crisis comparison "
    "(fewer meet the minimum message count in the January-to-April windows; see the placebo "
    "custodians column), so they have less power: a passing placebo does not exclude a "
    "pre-existing trend. Both placebo windows also lie before the change of the timestamp "
    "convention (see the record section), so the placebo cannot detect an artifact of it.",
    "The permutation p-values of H1–H4 treat weeks as exchangeable; weekly network metrics are "
    "autocorrelated, and a calibration test in the suite shows the test rejects far more often "
    "than its nominal level on autocorrelated series without a change. A small p alone is weak "
    "evidence here.",
    "Deduplication matches copies on the second they were sent. If two stored copies of one "
    "message carry different timestamp conventions (see the record section), they do not "
    "merge, so the months around the change may hold hidden duplicates; not checked.",
    "The H2 baseline placebo splits the baseline year at a fixed midpoint instead of searching "
    "a change week; a searched split could only make its jump larger, so this can only make H2 "
    "fail its check more clearly.",
    "The artifact checks were added after the first real-data run, because two hypotheses "
    "passed every pre-registered check yet looked implausibly strong. They are documented as a "
    "post-hoc amendment; a reader should weigh them as diagnostics, not as pre-registered tests.",
)

HYPOTHESIS_HEADERS = (
    "Hypothesis",
    "Claim",
    "Metric",
    "Scope",
    "Change week",
    "Effect",
    "Interval",
    "p",
    "Holm p",
    "Null z",
    "Leave-one-out range",
    "Robust variants",
    "Supported",
    "Confidence",
    "Headline",
)
RISK_COLUMNS = (
    "release_variant",
    "attacker",
    "n_targets",
    "unique_share",
    "median_anonymity_set",
    "reid_top1",
    "reid_ci_low",
    "reid_ci_high",
    "utility_effect_ratio",
    "finding_survives",
)
RISK_HEADERS = (
    "Release",
    "Attacker",
    "Targets",
    "Unique share",
    "Median anonymity set",
    "Re-identified (top-1)",
    "Interval low",
    "Interval high",
    "Effect ratio",
    "Finding survives",
)


class UnfilledPlaceholder(ContractViolation):
    """A document names a placeholder that no release table fills."""


@dataclass(frozen=True)
class ReleaseTables:
    data_quality: pl.DataFrame
    header_fields: pl.DataFrame
    hypotheses: pl.DataFrame
    risk: pl.DataFrame
    weekly_metrics: pl.DataFrame
    artifact_checks: pl.DataFrame
    exploratory: pl.DataFrame
    record_profile: pl.DataFrame
    community_groups: pl.DataFrame

    @classmethod
    def read(cls, ctx: StageContext) -> ReleaseTables:
        return cls(
            data_quality=ctx.read("data_quality"),
            header_fields=ctx.read("header_fields"),
            hypotheses=ctx.read("hypotheses"),
            risk=ctx.read("risk"),
            weekly_metrics=ctx.read("weekly_metrics"),
            artifact_checks=ctx.read("artifact_checks"),
            exploratory=ctx.read("exploratory"),
            record_profile=ctx.read("record_profile"),
            community_groups=ctx.read("community_groups"),
        )


# ---- the finding --------------------------------------------------------------------------


Row = Mapping[str, object]


def headline(hypotheses: pl.DataFrame) -> Row | None:
    rows = hypotheses.filter(pl.col("is_headline")).rows(named=True)
    if len(rows) > 1:
        raise ContractViolation(f"hypotheses: {len(rows)} headline rows, at most one allowed")
    return rows[0] if rows else None


def _f(row: Row, column: str) -> str:
    return format_value(row[column])


def _number(row: Row, column: str) -> float:
    value = row[column]
    if not isinstance(value, int | float):
        raise ContractViolation(f"{column}: expected a number")
    return float(value)


def claim(hypothesis: str) -> str:
    if hypothesis not in HYPOTHESIS_CLAIMS:
        raise ContractViolation("hypotheses: unknown hypothesis id")
    return HYPOTHESIS_CLAIMS[hypothesis]


def change_phrase(row: Row) -> str:
    if row["change_week"] is None:
        return "no single change week was estimated"
    return f"the change point is the week of {_f(row, 'change_week')}"


def _artifact_result(checks: pl.DataFrame, hypothesis: str) -> bool | str | None:
    """The hypothesis's artifact check result: True, False, None (could not run), or
    NO_CHECK when it has no artifact check."""
    rows = checks.filter(pl.col("hypothesis") == hypothesis).get_column("passes").to_list()
    return rows[0] if rows else NO_CHECK


def _names(hypotheses: list[str]) -> str:
    return ", ".join(sorted(hypotheses))


def no_headline_statement(hypotheses: pl.DataFrame, checks: pl.DataFrame) -> str:
    """Why no finding is claimed. Only hypotheses with `supported = yes` are named; a hypothesis
    that is not supported is never said to have passed anything."""
    supported = hypotheses.filter(pl.col("supported") == "yes").rows(named=True)
    if not supported:
        return (
            "No hypothesis is supported. Every outcome is listed below; a null result is a "
            "valid answer to the question."
        )
    result = {row["hypothesis"]: _artifact_result(checks, row["hypothesis"]) for row in supported}
    failed = [h for h, r in result.items() if r is False]
    not_run = [h for h, r in result.items() if r is None]
    sentences = ["No finding about the crisis year is claimed."]
    if failed:
        sentences.append(
            f"{_names(failed)} passed the pre-registered statistical tests but failed its check "
            "against a known artifact of the data (release/artifact_checks.csv): the apparent "
            "change is explained by how the data was collected and analysed, not by a "
            "detectable change in how people communicated."
        )
    if not_run:
        sentences.append(
            f"{_names(not_run)} passed the pre-registered statistical tests but its check "
            "against a known artifact of the data could not run, so that artifact is not ruled "
            "out."
        )
    for row in supported:
        if result[row["hypothesis"]] in (True, NO_CHECK):
            sentences.append(
                f"{row['hypothesis']} is supported but does not pass every robustness check "
                f"(confidence {row['confidence']}), so it is not the headline."
            )
    sentences.append("Every outcome is listed in the report.")
    return " ".join(sentences)


def headline_statement(hypotheses: pl.DataFrame, checks: pl.DataFrame) -> str:
    row = headline(hypotheses)
    if row is None:
        return no_headline_statement(hypotheses, checks)
    return (
        f"{row['hypothesis']} is supported: {claim(_f(row, 'hypothesis'))}. "
        f"Metric `{row['metric']}` in the {row['scope']} network; {change_phrase(row)}; "
        f"standardized effect of {_f(row, 'effect')} "
        f"(bootstrap interval {_f(row, 'ci_low')} to {_f(row, 'ci_high')}), "
        f"permutation p = {_f(row, 'p_perm')}, Holm-adjusted p = {_f(row, 'p_holm')}. "
        f"Confidence: {row['confidence']}."
    )


def evidence(row: Row) -> list[str]:
    return [
        f"Effect size: {_f(row, 'effect')} standard deviations against the baseline period, "
        f"block-bootstrap interval {_f(row, 'ci_low')} to {_f(row, 'ci_high')}.",
        f"Chance baseline: permutation p = {_f(row, 'p_perm')}; "
        f"{_f(row, 'null_z')} standard deviations from a null model that rewires recipients "
        "while keeping every sender's and recipient's volume.",
        f"Multiple testing: Holm-adjusted p = {_f(row, 'p_holm')} across all hypotheses.",
        f"Leaving out each mailbox in turn: effect between {_f(row, 'loo_min_effect')} and "
        f"{_f(row, 'loo_max_effect')}.",
        f"Sensitivity variants: {_f(row, 'robust_variants_passed')} of "
        f"{_f(row, 'robust_variants_total')} agree.",
    ]


def artifact_section(checks: pl.DataFrame) -> str:
    rows = [
        [
            r["hypothesis"],
            r["check"].replace("_", " "),
            format_value(r["statistic"]),
            f"{format_value(r['ci_low'])} to {format_value(r['ci_high'])}",
            format_value(r["n_units"]),
            {True: "passes", False: "fails", None: "not run"}[r["passes"]],
            r["note"],
        ]
        for r in checks.iter_rows(named=True)
    ]
    return "\n\n".join(
        (
            "### Checks against known artifacts",
            "Added after the first real-data run, which showed that the pre-registered checks "
            "could not separate a behavioural change from two artifacts: groups fixed on a "
            "baseline going stale (H2: fit groups on the first half of the baseline year and "
            "measure the jump into the calm second half; a jump above the threshold in "
            "docs/hypotheses.md fails), and a change in which mailboxes hold mail (H3: median "
            "change in each custodian's own share; the interval must lie below zero). "
            "A check that fails or cannot run caps confidence at low.",
            table(
                ["Hypothesis", "Check", "Statistic", "Interval", "Units", "Result", "Reading"],
                rows,
            ),
        )
    )


SUPPRESSED = "suppressed (fewer than k custodians)"


def _span_of(exploratory: pl.DataFrame) -> str:
    """`H5–H25`: the first and last hypothesis of the within-custodian table (released in
    hypothesis order)."""
    ids = exploratory.get_column("hypothesis").to_list()
    return f"{ids[0]}–{ids[-1]}" if ids else "the within-custodian hypotheses"


def exploratory_statement(exploratory: pl.DataFrame) -> str:
    """One sentence per hypothesis held true among H5–H25, or a sentence saying there is none.
    With none, each hypothesis that met every other part of its rule (placebo, leave-one-out)
    and failed only the retention check is named with that check's result."""
    rows = exploratory.filter(pl.col("outcome") == schemas.EXPLORATORY_CONFIDENT).rows(named=True)
    if not rows:
        return (
            "Among the within-custodian hypotheses, none reached the standard to be held true."
            + "".join(
                f" {r['hypothesis']} ({r['measure']}) met its stated rule (median change "
                f"{format_value(r['median_change'])}, interval {format_value(r['ci_low'])} to "
                f"{format_value(r['ci_high'])}) but {r['caveat']}: there the change is "
                f"{format_value(r['retention_median'])} (interval "
                f"{format_value(r['retention_ci_low'])} to "
                f"{format_value(r['retention_ci_high'])}). "
                "It is not established once how much inbox mail was kept is held fixed."
                for r in exploratory.filter(
                    pl.col("retention_passes").eq(False)
                    & pl.col("placebo_passes").eq(True)
                    & pl.col("loo_stable").eq(True)
                ).rows(named=True)
            )
        )
    parts = []
    for r in rows:
        text = (
            f"Held true: {r['hypothesis']} ({r['measure']}, predicted {r['direction']}): "
            f"median within-custodian change {format_value(r['median_change'])} "
            f"(interval {format_value(r['ci_low'])} to {format_value(r['ci_high'])}, "
            f"Holm-adjusted p = {format_value(r['p_holm'])}, "
            f"{format_value(r['custodians'])} custodians)"
        )
        if r["equalised_median"] is not None:
            text += (
                f"; with mail volume equalised, {format_value(r['equalised_median'])} "
                f"(interval {format_value(r['equalised_ci_low'])} to "
                f"{format_value(r['equalised_ci_high'])}, family-adjusted p = "
                f"{format_value(r['equalised_p_holm'])})"
            )
        parts.append(text + ".")
    return (
        " ".join(parts)
        + " Each was stated after the results of H1–H4 and before being computed (H25 also after"
        " every other result, as a post-hoc replication test), and each comparison crosses the"
        " change of the record described above, so a held-true result is a lead for confirmation"
        " on independent data rather than a pre-registered finding."
    )


def exploratory_section(exploratory: pl.DataFrame) -> str:
    rows = [
        [
            r["hypothesis"],
            r["measure"],
            r["direction"],
            format_value(r["custodians"]),
            format_value(r["median_change"]),
            f"{format_value(r['ci_low'])} to {format_value(r['ci_high'])}",
            format_value(r["p_holm"]),
            format_value(r["placebo_custodians"]),
            {True: "passes", False: "fails", None: SUPPRESSED}[r["placebo_passes"]],
            {True: "stable", False: "unstable", None: SUPPRESSED}[r["loo_stable"]],
            r["outcome"] or SUPPRESSED,
            r["caveat"] or "—",
        ]
        for r in exploratory.iter_rows(named=True)
    ]
    return "\n\n".join(
        (
            f"## Hypotheses {_span_of(exploratory)}",
            "Further hypotheses: H5–H24 stated by the project owner in two groups of ten, each "
            "committed before it was computed, and H25, stated in the review after every other "
            "result as a replication test of Diesner, Frantz and Carley (post hoc; recorded "
            "with their original numbers E1–E21 in docs/hypotheses-exploratory.md). Every "
            "comparison is a custodian against themselves between fixed windows (the crisis "
            "weeks against the same weeks a year earlier), with a pre-crisis placebo, "
            "leave-one-out and Holm's correction across all of them. A hypothesis is held true "
            "only if all of these pass. Mail-volume equalisation and the retention checks were "
            "added after results were seen and are labelled as such.",
            exploratory_statement(exploratory),
            table(
                [
                    "ID",
                    "Measure",
                    "Predicted",
                    "Custodians",
                    "Median change",
                    "Interval",
                    "Holm p",
                    "Placebo custodians",
                    "Placebo",
                    "Leave-one-out",
                    "Outcome",
                    "Caveat",
                ],
                rows,
            ),
        )
    )


def finding_section(hypotheses: pl.DataFrame, checks: pl.DataFrame) -> str:
    row = headline(hypotheses)
    parts = ["## The finding", headline_statement(hypotheses, checks), artifact_section(checks)]
    if row is not None:
        parts += [
            "### Evidence",
            bullets(evidence(row)),
            f"**Confidence**: {CONFIDENCE_WORDS[_f(row, 'confidence')]}.",
            "### Alternative explanations considered",
            bullets(ALTERNATIVE_EXPLANATIONS),
            "### What would falsify it",
            bullets(FALSIFIERS),
        ]
    return "\n\n".join(parts)


def hypothesis_row(row: Row) -> list[str]:
    return [
        _f(row, "hypothesis"),
        claim(_f(row, "hypothesis")),
        f"`{row['metric']}`",
        _f(row, "scope"),
        _f(row, "change_week"),
        _f(row, "effect"),
        f"{_f(row, 'ci_low')} to {_f(row, 'ci_high')}",
        _f(row, "p_perm"),
        _f(row, "p_holm"),
        _f(row, "null_z"),
        f"{_f(row, 'loo_min_effect')} to {_f(row, 'loo_max_effect')}",
        f"{_f(row, 'robust_variants_passed')} of {_f(row, 'robust_variants_total')}",
        _f(row, "supported"),
        _f(row, "confidence"),
        _f(row, "is_headline"),
    ]


def hypotheses_table(hypotheses: pl.DataFrame) -> str:
    return table(HYPOTHESIS_HEADERS, [hypothesis_row(r) for r in hypotheses.rows(named=True)])


def hypotheses_section(hypotheses: pl.DataFrame) -> str:
    return "\n\n".join(
        (
            "## All hypotheses",
            "Written down before the analysis ran on the real corpus. Every outcome is shown, "
            "including those not supported.",
            hypotheses_table(hypotheses),
        )
    )


def hypotheses_summary(hypotheses: pl.DataFrame) -> str:
    """Narrow version of the hypotheses table for a slide."""
    rows = [
        [
            row["hypothesis"],
            claim(row["hypothesis"]),
            _f(row, "effect"),
            f"{_f(row, 'ci_low')} to {_f(row, 'ci_high')}",
            _f(row, "p_holm"),
            row["supported"],
            row["confidence"],
        ]
        for row in hypotheses.rows(named=True)
    ]
    headers = ("Hypothesis", "Claim", "Effect", "Interval", "Holm p", "Supported", "Confidence")
    return table(headers, rows)


# ---- risk ---------------------------------------------------------------------------------


def risk_table(risk: pl.DataFrame) -> str:
    rows = risk.select(RISK_COLUMNS).rows()
    return table(RISK_HEADERS, [[format_value(v) for v in row] for row in rows])


def risk_summary(risk: pl.DataFrame) -> str:
    """Narrow version of the risk table for a slide."""
    rows = [
        [
            row["release_variant"],
            row["attacker"],
            _f(row, "unique_share"),
            _f(row, "reid_top1"),
            f"{_f(row, 'reid_ci_low')} to {_f(row, 'reid_ci_high')}",
            _f(row, "finding_survives"),
        ]
        for row in risk.rows(named=True)
    ]
    headers = ("Release", "Attacker", "Unique share", "Re-identified", "Interval", "Survives")
    return table(headers, rows)


def _risk_row(risk: pl.DataFrame, variant: str, attacker: str) -> Row:
    rows = risk.filter(
        (pl.col("release_variant") == variant) & (pl.col("attacker") == attacker)
    ).rows(named=True)
    if len(rows) != 1:
        raise ContractViolation(f"risk: expected one row for {variant}/{attacker}")
    return rows[0]


def risk_verdicts(risk: pl.DataFrame) -> list[str]:
    """One line per mitigated release and attacker: rate before and after, halved or not."""
    lines = []
    for variant, attacker in risk.select("release_variant", "attacker").rows():
        if variant == "R0":
            continue
        before = _risk_row(risk, "R0", attacker)
        after = _risk_row(risk, variant, attacker)
        halved = _number(after, "reid_top1") <= _number(before, "reid_top1") * MITIGATION_TARGET
        lines.append(
            f"{variant} against {attacker}: re-identified share {_f(before, 'reid_top1')} on R0, "
            f"{_f(after, 'reid_top1')} on {variant} "
            f"({'at least halved' if halved else 'not halved: target missed'}); "
            f"finding survives: {_f(after, 'finding_survives')}."
        )
    return lines


NO_HEADLINE_UTILITY = (
    'The effect ratio and "finding survives" columns are empty because there is no headline '
    "finding to recompute on the mitigated releases: they measure how much of the headline "
    "effect R1 and R2 keep. H5–H25 are computed in the finding stage on restricted data, not "
    "from a release, so the release mitigations do not change them."
)


def risk_section(risk: pl.DataFrame, k_min: int, has_headline: bool) -> str:
    variants = bullets(f"**{name}**: {text}" for name, text in RELEASE_VARIANTS.items())
    attackers = bullets(f"**{name}**: {text}" for name, text in ATTACKERS.items())
    utility_note = () if has_headline else (NO_HEADLINE_UTILITY,)
    return "\n\n".join(
        (
            "## Privacy and re-identification risk",
            f"Every published table meets a minimum group size of k = {k_min}. The risk of "
            "the person-level output R0 was tested by attacking it, not asserted. R1 and R2 "
            "hold no person-level records, so both person-level attacks return no guesses by "
            "construction: their re-identification rate of zero restates that design, it is "
            "not a measurement of their risk.",
            "Releases attacked:",
            variants,
            "Attackers:",
            attackers,
            risk_table(risk),
            *utility_note,
            "Before and after mitigation:",
            bullets(risk_verdicts(risk)),
        )
    )


# ---- report -------------------------------------------------------------------------------


def n2_limit(data_quality: pl.DataFrame) -> str:
    """The rule N2 risk, with the manual merge check from `data_quality` when one was run."""
    risk = (
        "Rule N2 merges addresses with the same local part under one registered domain, so it "
        "can merge two different people who share a local part across an ISP's regional "
        "subdomains"
    )
    manual = data_quality.filter(pl.col("step") == STEP_MANUAL).rows(named=True)
    if not manual:
        return f"{risk}; no manual check of merges was run."
    row = manual[0]
    text = (
        f"{risk}; a manual check of {format_value(row['count_in'])} sampled real merges found "
        f"{format_value(row['removed'])} wrong merges (precision {format_value(row['precision'])}, "
        f"exact binomial interval {format_value(row['precision_ci_low'])} to "
        f"{format_value(row['precision_ci_high'])})"
    )
    n2 = data_quality.filter(pl.col("step") == STEP_MANUAL_N2).rows(named=True)
    if n2:
        text += (
            f"; rule N2 accounts for {format_value(n2[0]['count_in'])} of the sampled merges "
            f"and {format_value(n2[0]['removed'])} of the wrong ones"
        )
    return text + "."


def outside_statement(community_groups: pl.DataFrame, k_min: int) -> str:
    """What the `other` bucket of the group tables is and how many people it holds."""
    rows = community_groups.filter(pl.col("group") == vocab.OTHER_GROUP).rows(named=True)
    if not rows:
        return (
            f"No `other` row is published in `community_groups.csv`: fewer than {k_min} people "
            "fall outside the groups, so none is shown."
        )
    return (
        "The `other` row of `community_groups.csv` is not a community: it holds the "
        f"{format_value(rows[0]['n_persons'])} people with no tie in the baseline period (in this "
        "corpus mostly people first seen after it) plus any community of fewer than "
        f"{k_min} people. Its ties are published like a group's, but the explorer does not draw "
        "it as a group: it labels these people as outside the baseline groups and states, for "
        "each week, the share of mail that involves them."
    )


def limits(data_quality: pl.DataFrame, community_groups: pl.DataFrame, k_min: int) -> list[str]:
    return [*LIMITS, n2_limit(data_quality), outside_statement(community_groups, k_min)]


def limits_section(data_quality: pl.DataFrame, community_groups: pl.DataFrame, k_min: int) -> str:
    return "\n\n".join(("## Limits", bullets(limits(data_quality, community_groups, k_min))))


def render_report(tables: ReleaseTables, config: Config) -> str:
    sections = (
        "# Report: headers-only network analysis of the public Enron email corpus",
        "Generated by the pipeline from the release tables in this directory; no number below "
        f"is typed by hand. Minimum group size k = {config.k_min}; seed {config.seed}.",
        quality.quality_section(tables.data_quality, tables.header_fields),
        record.record_section(tables.record_profile, tables.exploratory),
        finding_section(tables.hypotheses, tables.artifact_checks),
        hypotheses_section(tables.hypotheses),
        exploratory_section(tables.exploratory),
        risk_section(tables.risk, config.k_min, headline(tables.hypotheses) is not None),
        limits_section(tables.data_quality, tables.community_groups, config.k_min),
    )
    text = "\n\n".join(sections) + "\n"
    check_no_identifiers(text)
    return text


def check_no_identifiers(text: str) -> None:
    hits = len(IDENTIFIER.findall(text))
    if hits:
        raise PrivacyViolation(f"generated text holds {hits} identifier-shaped values")


# ---- documents ----------------------------------------------------------------------------


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _row_values(prefix: str, row: Row, skip: tuple[str, ...]) -> dict[str, str]:
    return {f"{prefix}_{col}": format_value(v) for col, v in row.items() if col not in skip}


def utility_phrase(risk: pl.DataFrame, top: Row | None) -> str:
    if top is None:
        return "With no finding claimed, there is no effect whose loss to measure."
    row = _risk_row(risk, "R1", "A1")
    return (
        f"The headline effect keeps a ratio of {format_value(row['utility_effect_ratio'])} of its "
        "restricted value."
    )


def charted_row(hypotheses: pl.DataFrame) -> Row | None:
    """The headline; failing that, the supported hypothesis with the largest effect (an
    apparent signal that failed its artifact check); None when nothing is supported."""
    row = headline(hypotheses)
    if row is not None:
        return row
    supported = hypotheses.filter(pl.col("supported") == "yes")
    if supported.is_empty():
        return None
    return supported.sort(pl.col("effect").abs(), descending=True).row(0, named=True)


def headline_chart(tables: ReleaseTables) -> str:
    """Mermaid line chart of the headline metric over the weeks, or a sentence if none."""
    row = charted_row(tables.hypotheses)
    if row is None:
        return "No hypothesis is supported, so there is no series to chart."
    series = tables.weekly_metrics.filter(
        (pl.col("scope") == row["scope"])
        & (pl.col("metric") == row["metric"])
        & (pl.col("variant") == DEFAULT_VARIANT)
        & pl.col("value").is_not_null()
    ).sort("week")
    weeks = ", ".join(f'"{format_value(w)}"' for w in series.get_column("week").to_list())
    values = ", ".join(format_value(v) for v in series.get_column("value").to_list())
    return "\n".join(
        (
            "```mermaid",
            "xychart-beta",
            f'    title "{row["hypothesis"]}: {row["metric"]}, {row["scope"]} network, weekly"',
            f"    x-axis [{weeks}]",
            f"    line [{values}]",
            "```",
        )
    )


def document_values(tables: ReleaseTables, config: Config) -> dict[str, str]:
    """The single placeholder -> value table for every document."""
    values: dict[str, str] = {"k_min": str(config.k_min), "seed": str(config.seed)}
    for row in tables.data_quality.rows(named=True):
        values.update(_row_values(f"dq_{slug(row['step'])}", row, ("order", "step")))
    for ruling, fields in quality.fields_by_ruling(tables.header_fields).items():
        values[f"fields_{ruling}"] = fields
    for row in tables.hypotheses.rows(named=True):
        values.update(_row_values(row["hypothesis"].lower(), row, ("hypothesis",)))
    for row in tables.risk.rows(named=True):
        prefix = f"risk_{row['release_variant'].lower()}_{row['attacker'].lower()}"
        values.update(_row_values(prefix, row, ("release_variant", "attacker")))
    top = headline(tables.hypotheses)
    if top is not None:
        values.update(_row_values("headline", top, ()))
        values["headline_claim"] = claim(_f(top, "hypothesis"))
    values.update(
        {
            "headline_statement": headline_statement(tables.hypotheses, tables.artifact_checks),
            "utility_phrase": utility_phrase(tables.risk, top),
            "exploratory_statement": exploratory_statement(tables.exploratory),
            "record_statement": record.record_statement(tables.record_profile, tables.exploratory),
            "record_table": record.profile_table(tables.record_profile),
            "record_chart": record.record_chart(tables.record_profile),
            "record_summary": record.record_summary(tables.record_profile, tables.exploratory),
            "replication_statement": record.replication_statement(tables.exploratory),
            "headline_chart": headline_chart(tables),
            "artifact_table": artifact_section(tables.artifact_checks).split("\n\n", 2)[2],
            "quality_table": quality.funnel_table(tables.data_quality),
            "header_table": quality.header_table(tables.header_fields),
            "hypotheses_table": hypotheses_table(tables.hypotheses),
            "hypotheses_summary": hypotheses_summary(tables.hypotheses),
            "risk_table": risk_table(tables.risk),
            "risk_summary": risk_summary(tables.risk),
            "risk_verdicts": bullets(risk_verdicts(tables.risk)),
            "limits": bullets(limits(tables.data_quality, tables.community_groups, config.k_min)),
        }
    )
    return values


def inject(text: str, values: Mapping[str, str]) -> str:
    """Replace every `{{name}}`; fail on an unknown name or a malformed placeholder."""
    missing = sorted({name for name in PLACEHOLDER.findall(text) if name not in values})
    if missing:
        raise UnfilledPlaceholder(f"no value for placeholders: {', '.join(missing)}")
    leftover = PLACEHOLDER.sub("", text)
    if "{{" in leftover or "}}" in leftover:
        raise UnfilledPlaceholder("malformed placeholder in document")
    return PLACEHOLDER.sub(lambda m: values[m.group(1)], text)
