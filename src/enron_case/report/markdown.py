"""Plain Markdown building blocks and the one way a table cell becomes text."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from datetime import date

SIGNIFICANT_DIGITS = 3
MISSING = "—"  # shown for a null or non-finite cell: suppressed, not measured or undefined


def format_float(value: float) -> str:
    """Fixed notation with three significant digits and no trailing zeros (0.002, 1.8, 12).
    NaN and ±inf (an effect that could not be computed) show as MISSING."""
    if not math.isfinite(value):
        return MISSING
    if value == 0:
        return "0"
    magnitude = math.floor(math.log10(abs(value)))
    decimals = max(0, SIGNIFICANT_DIGITS - 1 - magnitude)
    text = f"{value:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def format_value(value: object) -> str:
    """Text of one release table cell, as every document shows it."""
    if value is None:
        return MISSING
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format_float(value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def bullets(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
