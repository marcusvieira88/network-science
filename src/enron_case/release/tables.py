"""Release tables built from the counts side outputs and the finding and risk results.

Counts only: header field names and rulings come from `ingest_counts`, so this package never
imports ingest code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl
from scipy.stats import beta

from enron_case.contracts import schemas, vocab
from enron_case.errors import ContractViolation

STEP_PARSE = "files parsed"
STEP_DEDUPE = "deduplicate"
STEP_IDENTITY = "resolve identities"
RULE_DEDUPE = "exact+subset"
RULE_IDENTITY = "N1-N4"
STEP_MANUAL = "manual merge check"
RULE_MANUAL = "seeded sample, judged by a person"
STEP_MANUAL_RULE = "manual merge check: rule {rule}"
STEP_REJECTED = "rejected files: {reason}"
RULE_REJECTED = "file not parsed: no clean end of the header, or outside a mailbox folder"
STEP_EXACT = "deduplicate: exact copies"
RULE_EXACT = "copies merged by the exact key alone (sender, second, recipient set)"
STEP_SUBSET = "deduplicate: subset copies"
RULE_SUBSET = "copies of messages that needed a subset merge, with any exact copies they had"
STEP_FLAG = "flag: {flag}"
FLAG_NAMES = {
    "bad_address": "bad address",
    "date_out_of_range": "date out of range",
    "mass_mailing": "mass mailing",
    "no_recipients": "no recipients",
    "self_only": "self-only",
}
RULE_FLAG_EXCLUDED = "messages flagged; kept, but left out of the network"
RULE_FLAG_KEPT = "messages flagged; kept in the network"
STEP_EVENTS = "events in the network"
RULE_EVENTS = "sender-recipient events of messages without an exclusion flag"


def require(counts: dict[str, Any], file: str, key: str) -> object:
    """A counts value, or a ContractViolation naming the missing file or key."""
    if key not in counts:
        raise ContractViolation(f"counts '{file}' lack '{key}'")
    value: object = counts[key]
    return value


def require_int(counts: dict[str, Any], file: str, key: str) -> int:
    value = require(counts, file, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"counts '{file}': '{key}' is not an integer")
    return value


def require_rate(counts: dict[str, Any], file: str, key: str) -> float | None:
    """A precision or recall: a number, or null where there is no ground truth."""
    value = require(counts, file, key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContractViolation(f"counts '{file}': '{key}' is not a number")
    return float(value)


def _count(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"counts: the count of '{field}' is not an integer")
    return value


def _ruling(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation(f"ingest_counts: ruling of '{field}' is not a string")
    return value


def require_mapping(counts: dict[str, Any], file: str, key: str) -> dict[str, object]:
    value = require(counts, file, key)
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ContractViolation(f"counts '{file}': '{key}' is not a mapping")
    return value


@dataclass(frozen=True)
class Step:
    """One `data_quality` row before it is numbered."""

    step: str
    count_in: int
    count_out: int
    rule: str | None = None
    precision: float | None = None
    recall: float | None = None
    precision_ci: tuple[float | None, float | None] = (None, None)


def data_quality(
    ingest: dict[str, Any],
    clean: dict[str, Any],
    identity: dict[str, Any],
    pseudo: dict[str, Any],
    ci_level: float,
    manual: dict[str, Any] | None = None,
) -> pl.DataFrame:
    """One row per pipeline step: what went in, what came out, the rule and its measured
    precision and recall where ground truth exists. The main steps come first (with the manual
    merge check and its per-rule composition when a review was run), then the detail of the
    funnel: rejected files by reason, the exact/subset dedupe split, the five message flags and
    events in and out of the network.

    Every count is of files, messages or events (or judged merges), never of persons, so no
    k-suppression applies: such a count does not describe a group of people."""
    files_seen = require_int(ingest, "ingest_counts", "files_seen")
    files_parsed = require_int(ingest, "ingest_counts", "files_parsed")
    records = require_int(clean, "clean_counts", "records_in")
    messages = require_int(clean, "clean_counts", "messages_out")
    steps = [
        Step(STEP_PARSE, files_seen, files_parsed),
        Step(
            STEP_DEDUPE,
            records,
            messages,
            RULE_DEDUPE,
            require_rate(clean, "clean_counts", "dedupe_precision"),
            require_rate(clean, "clean_counts", "dedupe_recall"),
        ),
        Step(
            STEP_IDENTITY,
            require_int(identity, "identity_counts", "addresses"),
            require_int(identity, "identity_counts", "entities"),
            RULE_IDENTITY,
            require_rate(identity, "identity_counts", "precision"),
            require_rate(identity, "identity_counts", "recall"),
        ),
        *_manual_steps(manual or {}, ci_level),
        *_rejected_steps(ingest, files_seen, files_parsed),
        *_dedupe_steps(clean, records, messages),
        *_flag_steps(clean, messages),
        _events_step(pseudo),
    ]
    return pl.DataFrame(
        [
            {
                "order": order,
                "step": s.step,
                "count_in": s.count_in,
                "count_out": s.count_out,
                "removed": s.count_in - s.count_out,
                "rule": s.rule,
                "precision": s.precision,
                "recall": s.recall,
                "precision_ci_low": s.precision_ci[0],
                "precision_ci_high": s.precision_ci[1],
            }
            for order, s in enumerate(steps, start=1)
        ],
        schema=schemas.table("data_quality").polars_schema,
    )


def clopper_pearson(successes: int, trials: int, level: float) -> tuple[float, float]:
    """Exact two-sided binomial interval for a proportion (Clopper-Pearson)."""
    tail = (1 - level) / 2
    low = 0.0 if successes == 0 else float(beta.ppf(tail, successes, trials - successes + 1))
    high = (
        1.0 if successes == trials else float(beta.ppf(1 - tail, successes + 1, trials - successes))
    )
    return low, high


def _judged(name: str, checked: int, correct: int, rule: str, level: float) -> Step:
    return Step(
        name,
        checked,
        correct,
        rule,
        correct / checked,
        precision_ci=clopper_pearson(correct, checked, level),
    )


def _manual_steps(manual: dict[str, Any], level: float) -> list[Step]:
    """The manual merge check and, when the review stored it, one row per identity rule. A
    review run before per-rule counts were kept has none; that is not an error."""
    checked = manual.get("manual_checked")
    if not checked:
        return []
    checked = require_int(manual, "identity_manual", "manual_checked")
    correct = require_int(manual, "identity_manual", "manual_correct")
    steps = [_judged(STEP_MANUAL, checked, correct, RULE_MANUAL, level)]
    if "manual_by_rule" not in manual:
        return steps
    by_rule = require_mapping(manual, "identity_manual", "manual_by_rule")
    per_rule = {
        rule: (
            require_int(_mapping(counts, rule), "identity_manual", "checked"),
            require_int(_mapping(counts, rule), "identity_manual", "correct"),
        )
        for rule, counts in sorted(by_rule.items())
    }
    if sum(c for c, _ in per_rule.values()) != checked or (
        sum(k for _, k in per_rule.values()) != correct
    ):
        raise ContractViolation("identity_manual: per-rule counts do not add up to the total")
    return steps + [
        _judged(STEP_MANUAL_RULE.format(rule=rule), c, k, RULE_MANUAL, level)
        for rule, (c, k) in per_rule.items()
    ]


def _mapping(value: object, key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractViolation(f"identity_manual: counts of rule '{key}' are not a mapping")
    return value


def _rejected_steps(ingest: dict[str, Any], files_seen: int, files_parsed: int) -> list[Step]:
    """One row per rejection reason; the reasons must account for every unparsed file."""
    rejected = {
        reason: _count(n, reason)
        for reason, n in require_mapping(ingest, "ingest_counts", "rejected").items()
    }
    if sum(rejected.values()) != files_seen - files_parsed:
        raise ContractViolation("ingest_counts: rejected files do not reconcile with parsed")
    return [
        Step(
            STEP_REJECTED.format(reason=reason.replace("_", " ")),
            files_seen,
            files_seen - n,
            RULE_REJECTED,
        )
        for reason, n in sorted(rejected.items())
    ]


def _dedupe_steps(clean: dict[str, Any], records: int, messages: int) -> list[Step]:
    exact = require_int(clean, "clean_counts", "removed_exact")
    subset = require_int(clean, "clean_counts", "removed_subset")
    if records - exact - subset != messages:
        raise ContractViolation("clean_counts: exact and subset removals do not reconcile")
    after_exact = records - exact
    return [
        Step(STEP_EXACT, records, after_exact, RULE_EXACT),
        Step(STEP_SUBSET, after_exact, messages, RULE_SUBSET),
    ]


def _flag_steps(clean: dict[str, Any], messages: int) -> list[Step]:
    """The five message flags, zero when absent. Flagged messages are kept in `messages`."""
    flags = {
        flag: _count(n, flag) for flag, n in require_mapping(clean, "clean_counts", "flags").items()
    }
    unknown = sorted(set(flags) - set(FLAG_NAMES))
    if unknown:
        raise ContractViolation(f"clean_counts: {len(unknown)} unknown message flags")
    return [
        Step(
            STEP_FLAG.format(flag=name),
            messages,
            messages - flags.get(flag, 0),
            RULE_FLAG_EXCLUDED if flag in vocab.NETWORK_EXCLUSION_FLAGS else RULE_FLAG_KEPT,
        )
        for flag, name in FLAG_NAMES.items()
    ]


def _events_step(pseudo: dict[str, Any]) -> Step:
    events = require_int(pseudo, "pseudo_counts", "events")
    in_network = require_int(pseudo, "pseudo_counts", "events_in_network")
    return Step(STEP_EVENTS, events, in_network, RULE_EVENTS)


def header_fields(ingest: dict[str, Any]) -> pl.DataFrame:
    """Every header field name seen, how often, and the ruling the parser applied to it."""
    occurrences = {
        name: _count(n, name)
        for name, n in require_mapping(ingest, "ingest_counts", "header_fields").items()
    }
    rulings = {
        name: _ruling(r, name)
        for name, r in require_mapping(ingest, "ingest_counts", "header_rulings").items()
    }
    unruled = sorted(set(occurrences) - set(rulings))
    if unruled:
        raise ContractViolation(f"ingest_counts: {len(unruled)} header fields without a ruling")
    known = {name: n for name, n in occurrences.items() if name in vocab.KNOWN_HEADER_FIELDS}
    other = sum(n for name, n in occurrences.items() if name not in vocab.KNOWN_HEADER_FIELDS)
    names = list(known)
    counts = list(known.values())
    labels = [rulings[name] for name in known]
    if other:
        # Unknown names are never published: they can be fragments of message text.
        names.append(vocab.OTHER_HEADER_FIELD)
        counts.append(other)
        labels.append("dropped")
    return pl.DataFrame(
        {"field": names, "occurrences": counts, "ruling": labels},
        schema=schemas.table("header_fields").polars_schema,
    )


def artifact_checks(results: pl.DataFrame, k_min: int) -> pl.DataFrame:
    """The artifact checks; a count of custodians below k is suppressed."""
    return results.with_columns(
        pl.when((pl.col("check") == "within_custodian") & (pl.col("n_units") < k_min))
        .then(None)
        .otherwise(pl.col("n_units"))
        .alias("n_units")
    )


def exploratory(results: pl.DataFrame, k_min: int) -> pl.DataFrame:
    """H5–H24 results. A comparison over fewer than k custodians is suppressed with its
    statistics (the count and every number derived from it)."""
    crisis = (
        "custodians",
        "median_change",
        "ci_low",
        "ci_high",
        "p",
        "p_holm",
        "equalised_median",
        "equalised_ci_low",
        "equalised_ci_high",
        "equalised_p",
        "retention_median",
        "retention_ci_low",
        "retention_ci_high",
        "retention_passes",
    )
    placebo = ("placebo_custodians", "placebo_median", "placebo_ci_low", "placebo_ci_high")
    # The outcome and the leave-one-out flag are derived from the crisis comparison, and the
    # placebo flag from the placebo comparison: below k they would reveal its sign and strength.
    crisis_derived = (*crisis, "outcome", "loo_stable")
    placebo_derived = (*placebo, "placebo_passes")
    small_crisis = pl.col("custodians") < k_min
    small_placebo = pl.col("placebo_custodians") < k_min
    return results.with_columns(
        *[pl.when(small_crisis).then(None).otherwise(pl.col(c)).alias(c) for c in crisis_derived],
        *[pl.when(small_placebo).then(None).otherwise(pl.col(c)).alias(c) for c in placebo_derived],
    )
