"""Report section "what we found in the data": the cleaning funnel and the header rulings."""

from __future__ import annotations

import polars as pl

from enron_case.errors import ContractViolation
from enron_case.report.markdown import format_value, table

FUNNEL_HEADERS = ("Step", "In", "Out", "Removed", "Rule", "Precision", "Recall")
FUNNEL_COLUMNS = ("step", "count_in", "count_out", "removed", "rule", "precision", "recall")
HEADER_HEADERS = ("Header field", "Occurrences", "Ruling")
HEADER_COLUMNS = ("field", "occurrences", "ruling")

RULING_MEANING = {
    "usable": "kept as metadata; time is truncated to the hour",
    "identifier": "used inside the ingest zone only, then pseudonymized or discarded",
    "content": "never stored",
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


def ruling_legend(header_fields: pl.DataFrame) -> str:
    rulings = sorted(set(header_fields.get_column("ruling").to_list()))
    unknown = [r for r in rulings if r not in RULING_MEANING]
    if unknown:
        raise ContractViolation(f"header_fields: {len(unknown)} unknown rulings")
    return "\n".join(f"- **{r}**: {RULING_MEANING[r]}" for r in rulings)


def quality_section(data_quality: pl.DataFrame, header_fields: pl.DataFrame) -> str:
    return "\n\n".join(
        (
            "## What we found in the data",
            "### Cleaning funnel",
            "Counts before and after each cleaning step. Precision and recall are measured "
            "against ground truth where it exists; a dash means not measured.",
            funnel_table(data_quality),
            "### Header fields and where the line is",
            "Every header field name seen in the corpus, how often, and how it was ruled. "
            "Only field names and counts are reported; no value is ever read out.",
            header_table(header_fields),
            ruling_legend(header_fields),
        )
    )
