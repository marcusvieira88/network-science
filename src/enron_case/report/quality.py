"""Report section "what we found in the data": the cleaning funnel and the header rulings."""

from __future__ import annotations

import polars as pl

from enron_case.contracts import vocab
from enron_case.errors import ContractViolation
from enron_case.report.markdown import format_value, table

FUNNEL_HEADERS = (
    "Step",
    "In",
    "Out",
    "Removed",
    "Rule",
    "Precision",
    "Recall",
    "Precision low",
    "Precision high",
)
FUNNEL_COLUMNS = (
    "step",
    "count_in",
    "count_out",
    "removed",
    "rule",
    "precision",
    "recall",
    "precision_ci_low",
    "precision_ci_high",
)
HEADER_HEADERS = ("Header field", "Occurrences", "Ruling")
HEADER_COLUMNS = ("field", "occurrences", "ruling")

IDENTIFIER = "identifier"
RULING_MEANING = {
    "usable": "kept as metadata; time is truncated to the hour",
    IDENTIFIER: "used inside the ingest zone only, then pseudonymized or discarded",
    "content": "never decoded, parsed, held, stored or logged: the line is discarded as the "
    "header is scanned. The folder class comes from the archive path, where a folder name is "
    "reduced at once to one of four classes and never kept",
    "technical": "used for diagnostics inside the ingest zone, then discarded",
    "dropped": "dropped by the parser",
}


def funnel_table(data_quality: pl.DataFrame) -> str:
    rows = data_quality.select(FUNNEL_COLUMNS).rows()
    return table(FUNNEL_HEADERS, [[format_value(v) for v in row] for row in rows])


def header_table(header_fields: pl.DataFrame) -> str:
    rows = header_fields.select(HEADER_COLUMNS).rows()
    return table(HEADER_HEADERS, [[format_value(v) for v in row] for row in rows])


def fields_by_ruling(header_fields: pl.DataFrame) -> dict[str, str]:
    """Ruling -> comma-separated field names, in the table's field order."""
    out: dict[str, list[str]] = {}
    for field, ruling in header_fields.select("field", "ruling").rows():
        out.setdefault(ruling, []).append(field)
    return {ruling: ", ".join(fields) for ruling, fields in out.items()}


def _meaning(ruling: str, fields: list[str]) -> str:
    """What a ruling means; for identifiers, which of the fields seen are not even retained."""
    not_retained = [f for f in fields if f in vocab.IDENTIFIERS_NOT_RETAINED]
    if ruling != IDENTIFIER or not not_retained:
        return RULING_MEANING[ruling]
    return (
        f"{RULING_MEANING[ruling]}; {', '.join(not_retained)}: direct identifier, not retained "
        "(dropped by the parser, so it never enters the ingest zone)"
    )


def ruling_legend(header_fields: pl.DataFrame) -> str:
    by_ruling: dict[str, list[str]] = {}
    for field, ruling in header_fields.select("field", "ruling").rows():
        by_ruling.setdefault(ruling, []).append(field)
    unknown = [r for r in by_ruling if r not in RULING_MEANING]
    if unknown:
        raise ContractViolation(f"header_fields: {len(unknown)} unknown rulings")
    return "\n".join(f"- **{r}**: {_meaning(r, by_ruling[r])}" for r in sorted(by_ruling))


def quality_section(data_quality: pl.DataFrame, header_fields: pl.DataFrame) -> str:
    return "\n\n".join(
        (
            "## What we found in the data",
            "### Cleaning funnel",
            "Counts before and after each cleaning step. Precision and recall are measured "
            "against ground truth, which exists for the synthetic corpus only; a dash means "
            "not measured, as for every step on the real corpus. There, the manual merge check "
            "estimates precision from a sample judged by a person, with its exact binomial "
            "(Clopper-Pearson) interval next to it, and gives no recall. The main steps "
            "come first, then their detail: rejected files by reason, the exact and subset "
            "parts of deduplication, each message flag, messages without a timestamp, and "
            "events in and out of the network. "
            "Every count is of files, messages or events, not persons, so no minimum group "
            "size applies. Flagged messages are kept; all flags except a bad address take the "
            "message out of the network. The mass mailing flag counts distinct recipient "
            "addresses above the recipient cap, before identity resolution; the recipient-cap "
            "network variant counts recipient entities after it, so one person's aliases count "
            "once there.",
            funnel_table(data_quality),
            "### Header fields and where the line is",
            "Every header field name seen in the corpus, how often, and how it was ruled. "
            "Only field names and counts are published, never the value of a field. "
            f"`{vocab.OTHER_HEADER_FIELD}` is not a field: it counts the occurrences of every "
            "name without a ruling, whose spelling is not kept.",
            header_table(header_fields),
            ruling_legend(header_fields),
        )
    )
