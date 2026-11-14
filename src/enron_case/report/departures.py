"""Report section "did custodians leave during the crisis?" (`departures`, `departure_tests`, H26).

Every sentence is built from the two release tables; a suppressed count reads "fewer than k".
"""

from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from enron_case.config import CRISIS_SPLIT, HYPOTHESES_STATED, Config
from enron_case.contracts import schemas
from enron_case.errors import ContractViolation
from enron_case.report.markdown import bullets, format_value, table

Row = Mapping[str, object]
CRISIS, REFERENCE, PLACEBO_AFTER, PLACEBO_BEFORE = schemas.DEPARTURE_WINDOWS
SPLIT_BEFORE, SPLIT_FROM = schemas.DEPARTURE_SPLITS
HIGH, MODERATE, LOW, NOT_ESTABLISHED = schemas.DEPARTURE_OUTCOMES
FAMILY_BOUND, BELOW_ALPHA, ALPHA_OR_ABOVE, NOT_COMPUTABLE = schemas.P_BANDS

PERIOD_HEADERS = ("Period", "From", "To", "At risk", "Departures", "Record ends", "Share departed")
PERIOD_COLUMNS = (
    "period",
    "period_start",
    "period_end",
    "at_risk",
    "departures",
    "record_ends",
    "hazard",
)
TEST_HEADERS = (
    "Variant",
    "In the rule",
    "Crisis share above reference",
    "p (crisis against reference)",
    "Placebo p",
    "Above every earlier window",
)
CONFIDENCE = {
    HIGH: "high",
    MODERATE: "moderate",
    LOW: "low (a lead, not a finding)",
}
LIMITS = (
    "Custodians are the people whose mailboxes were collected, mostly senior staff; a departure "
    "among them is not a count of layoffs, and the mailboxes were chosen for an investigation.",
    "A silence while mail keeps arriving is also what leave, a role without email, an assistant "
    "sending on someone's behalf or an address that identity resolution did not merge look "
    "like; the successor variant covers only the last, and only partly.",
    "Inbox retention grows in the crisis, which makes a live mailbox easier to see; the live 8 "
    "variant asks for twice the evidence.",
    "A message to a custodian can sit in another custodian's mailbox through a Bcc that the "
    "copy does not show; it would count as mail only the first mailbox holds. Not corrected.",
    "Departures after the bankruptcy filing (the layoffs that followed it) fall after the crisis "
    "window and are not tested; their silences reach into the next year, when the record thins.",
)


def _band_text(band: object, alpha: float) -> str:
    texts = {
        FAMILY_BOUND: f"below {format_value(alpha)}/{HYPOTHESES_STATED}",
        BELOW_ALPHA: f"below {format_value(alpha)}",
        ALPHA_OR_ABOVE: f"{format_value(alpha)} or above",
        NOT_COMPUTABLE: "not computable",
    }
    return texts.get(str(band), format_value(band))


def _p_text(row: Row, p: str, band: str, alpha: float) -> str:
    """The p-value where it is published, otherwise its band (a dash when both are hidden)."""
    if row[p] is not None:
        return f"p = {format_value(row[p])}"
    if row[band] is None:
        return format_value(None)
    return f"p {_band_text(row[band], alpha)}"


def _count(row: Row, column: str, k_min: int) -> str:
    value = row[column]
    return f"fewer than {k_min}" if value is None else format_value(value)


def _period(periods: pl.DataFrame, name: str) -> Row:
    rows = periods.filter(pl.col("period") == name).rows(named=True)
    if not rows:
        raise ContractViolation(f"departures: no row for period '{name}'")
    return rows[0]


def _primary(tests: pl.DataFrame) -> Row:
    rows = tests.filter(pl.col("variant") == schemas.DEPARTURE_PRIMARY).rows(named=True)
    if len(rows) != 1:
        raise ContractViolation("departure_tests: exactly one primary row expected")
    return rows[0]


def _share(row: Row, k_min: int) -> str:
    """Departures of the custodians at risk, with the share where it is published."""
    text = f"{_count(row, 'departures', k_min)} of {_count(row, 'at_risk', k_min)} at risk"
    if row["hazard"] is None:
        return text
    return f"{text} (share {format_value(row['hazard'])})"


def _reasons(primary: Row, crisis: Row, k_min: int, alpha: float) -> list[str]:
    """Which necessary conditions of the rule failed, in the order the rule states them."""
    reasons = []
    if crisis["departures"] is None:
        reasons.append(f"fewer than {k_min} custodians departed in the crisis window")
    if primary["p_band"] not in (FAMILY_BOUND, BELOW_ALPHA):
        reasons.append(
            "the crisis share is not significantly above the same weeks a year earlier "
            f"({_p_text(primary, 'p', 'p_band', alpha)})"
        )
    if not primary["above_rolling"]:
        reasons.append("an earlier window of the same length had at least as high a share")
    if primary["placebo_p_band"] != ALPHA_OR_ABOVE:
        reasons.append(
            "the pre-crisis placebo does not pass "
            f"({_p_text(primary, 'placebo_p', 'placebo_p_band', alpha)})"
        )
    return reasons


def _variant_sentence(tests: pl.DataFrame, alpha: float) -> str:
    ruled = tests.filter(pl.col("in_rule") & (pl.col("variant") != schemas.DEPARTURE_PRIMARY))
    direction = ruled.filter(pl.col("crisis_above_reference").fill_null(False)).height
    significant = ruled.filter(pl.col("p_band").is_in([FAMILY_BOUND, BELOW_ALPHA])).height
    hidden = ruled.filter(pl.col("p_band").is_null()).height
    text = (
        f"Of the {ruled.height} robustness variants in the rule, {direction} keep the crisis "
        f"share above the reference share and {significant} keep p below {format_value(alpha)}"
    )
    if hidden:
        verb = "publishes" if hidden == 1 else "publish"
        text += f"; {hidden} {verb} no comparison, because a window has too few custodians at risk"
    return text + "."


def _leave_one_out(row: Row) -> str:
    if row["p_band"] not in (FAMILY_BOUND, BELOW_ALPHA):
        return "leave-one-out does not apply, since the test itself does not pass."
    kept = "keeps" if row["loo_stable"] else "does not keep"
    return f"leaving each custodian out in turn {kept} the test and the rolling comparison."


def _any_silence_sentence(tests: pl.DataFrame) -> str:
    """The variant that counts every silence bounds what treating record ends as departures
    could hide (the end of collection turns late departures into record ends)."""
    rows = tests.filter(~pl.col("in_rule")).rows(named=True)
    if not rows or rows[0]["p_band"] is None:
        return ""
    row = rows[0]
    significant = row["p_band"] in (FAMILY_BOUND, BELOW_ALPHA)
    return (
        f" Counting every silence, record ends included (variant {row['variant']}), the crisis "
        f"share is {'' if significant else 'still not '}significantly above a year earlier."
    )


def _power_sentence(primary: Row, periods: pl.DataFrame) -> str:
    """How large a wave the test could see at these numbers at risk."""
    needed = primary["detectable_departures"]
    if needed is None:
        return ""
    crisis = _period(periods, CRISIS)
    text = (
        f"Power: even with no departure a year earlier, the crisis window would have needed at "
        f"least {format_value(needed)} departures of {format_value(crisis['at_risk'])} at risk "
        "for significance, so the test can see only a large wave"
    )
    placebo = primary["placebo_detectable_departures"]
    after = _period(periods, PLACEBO_AFTER)
    if placebo is not None and after["at_risk"] is not None:
        text += (
            f"; the placebo would have needed {format_value(placebo)} of "
            f"{format_value(after['at_risk'])}, so its passing shows little"
        )
    return text + "."


def _split_sentence(periods: pl.DataFrame, k_min: int) -> str:
    before, after = _period(periods, SPLIT_BEFORE), _period(periods, SPLIT_FROM)
    if before["departures"] is None:
        return (
            f"Split at {format_value(CRISIS_SPLIT)} (third-quarter loss announced), at least one "
            f"part holds fewer than {k_min} departures, so neither is published."
        )
    return (
        f"Of the crisis departures, {format_value(before['departures'])} began before "
        f"{format_value(CRISIS_SPLIT)} (third-quarter loss announced) and "
        f"{format_value(after['departures'])} from then on."
    )


def departure_statement(periods: pl.DataFrame, tests: pl.DataFrame, config: Config) -> str:
    """The outcome of H26 with its evidence, whatever it is."""
    k_min, alpha = config.k_min, config.alpha
    primary = _primary(tests)
    crisis, reference = _period(periods, CRISIS), _period(periods, REFERENCE)
    evidence = (
        f"Custodians who stopped sending for {config.departure_silence_weeks} weeks or more "
        f"while their own mailbox kept receiving mail: {_share(crisis, k_min)} in the crisis "
        f"window, against {_share(reference, k_min)} in the same weeks a year earlier "
        f"(one-sided Fisher {_p_text(primary, 'p', 'p_band', alpha)}). Record ends (the "
        f"mailbox stops holding mail too): {_count(crisis, 'record_ends', k_min)} in the crisis "
        f"window, {_count(reference, 'record_ends', k_min)} in the reference window."
    )
    rolling = (
        f" The crisis share is {'above' if primary['above_rolling'] else 'not above'} every one "
        f"of the {format_value(primary['rolling_windows'])} earlier windows of the same length "
        f"with at least {config.departure_rolling_min_at_risk} custodians at risk; the "
        f"pre-crisis placebo has {_p_text(primary, 'placebo_p', 'placebo_p_band', alpha)}; "
        f"{_leave_one_out(primary)} {_variant_sentence(tests, alpha)}"
        f"{_any_silence_sentence(tests)} {_power_sentence(primary, periods)}"
    )
    outcome = str(primary["outcome"])
    if outcome == NOT_ESTABLISHED:
        reasons = "; ".join(_reasons(primary, crisis, k_min, alpha))
        verdict = f" No departure wave can be established: {reasons}."
    else:
        verdict = (
            " Custodians stopped sending while their mailbox kept receiving at a higher rate "
            "during the crisis than in the same weeks a year earlier and than in any comparable "
            f"earlier window. Confidence: {CONFIDENCE[outcome]}."
        )
    return evidence + rolling + verdict + " " + _split_sentence(periods, k_min)


def departure_summary(tests: pl.DataFrame) -> str:
    """The outcome in one sentence, for the decision record and the slides."""
    outcome = str(_primary(tests)["outcome"])
    if outcome == NOT_ESTABLISHED:
        return "No wave of custodian departures in the crisis can be established."
    return f"More custodians went quiet with a live mailbox than before; confidence: {outcome}."


def periods_table(periods: pl.DataFrame) -> str:
    rows = periods.select(PERIOD_COLUMNS).rows()
    return table(PERIOD_HEADERS, [[format_value(v) for v in row] for row in rows])


def tests_table(tests: pl.DataFrame, alpha: float) -> str:
    rows = [
        [
            str(row["variant"]),
            format_value(row["in_rule"]),
            format_value(row["crisis_above_reference"]),
            _p_text(row, "p", "p_band", alpha),
            _p_text(row, "placebo_p", "placebo_p_band", alpha),
            format_value(row["above_rolling"]),
        ]
        for row in tests.rows(named=True)
    ]
    return table(TEST_HEADERS, rows)


def departure_section(periods: pl.DataFrame, tests: pl.DataFrame, config: Config) -> str:
    return "\n\n".join(
        (
            "## Did custodians leave during the crisis? (H26, post hoc)",
            "Stated in docs/hypotheses-exploratory.md (O1) after every other result and before "
            "it was computed. A custodian at risk at a window's start (sending and receiving in "
            f"at least {config.departure_active_weeks} of the {config.departure_lookback_weeks} "
            "weeks before, and not already silent) **departs** when they send nothing for "
            f"{config.departure_silence_weeks} weeks while, in at least "
            f"{config.departure_live_weeks} of those weeks, their mailbox receives mail that "
            "only it can hold (from a non-custodian, to no other custodian). If that mail stops "
            "too, the silence is a **record end**: the mailbox was no longer collected, which "
            "is not a departure. Weeks are read from the presence of mail, not from hours or "
            "volumes. The crisis window is compared with the same weeks a year earlier (one-sided "
            "Fisher exact test), with a pre-crisis placebo, with every earlier window of the same "
            "length, leaving each custodian out, and under the robustness variants. Counts below "
            "k are suppressed; a p-value is shown only when every count it comes from reaches "
            "k, otherwise its band.",
            departure_statement(periods, tests, config),
            periods_table(periods),
            tests_table(tests, config.alpha),
            bullets(LIMITS),
        )
    )
