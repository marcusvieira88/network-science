"""Cell formatting in report/markdown.py."""

from __future__ import annotations

import math

import pytest

from enron_case.report.markdown import MISSING, format_float, format_value


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_render_as_missing(value: float) -> None:
    assert format_float(value) == MISSING == "—"
    assert format_value(value) == "—"


@pytest.mark.parametrize(
    ("value", "text"), [(0.002, "0.002"), (1.8, "1.8"), (12.0, "12"), (0.0, "0")]
)
def test_finite_numbers_keep_three_significant_digits(value: float, text: str) -> None:
    assert format_float(value) == text
