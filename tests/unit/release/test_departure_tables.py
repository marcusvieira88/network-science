"""H26 release tables (release/tables.py): what may be published under k."""

from __future__ import annotations

from datetime import date

import polars as pl

from enron_case.contracts import schemas
from enron_case.release import kanon, tables

K = 5
DAY = date(2001, 8, 14)


def periods(rows: list[tuple[str, int, int, int | None]]) -> pl.DataFrame:
    """(period, at risk, departures, record ends) rows in contract shape."""
    return pl.DataFrame(
        [
            {
                "order": order,
                "period": period,
                "period_start": DAY,
                "period_end": DAY,
                "at_risk": at_risk,
                "departures": departed,
                "record_ends": ends,
                "hazard": departed / at_risk,
            }
            for order, (period, at_risk, departed, ends) in enumerate(rows, start=1)
        ],
        schema=schemas.table("departure_results").polars_schema,
    )


def cell(df: pl.DataFrame, period: str, column: str) -> object:
    return df.filter(pl.col("period") == period).get_column(column).item()


def test_departures_below_k_are_suppressed_with_their_share() -> None:
    out = tables.departures(periods([("crisis", 60, 3, 10), ("reference", 30, 6, 5)]), K)
    assert cell(out, "crisis", "departures") is None
    assert cell(out, "crisis", "hazard") is None
    assert cell(out, "crisis", "at_risk") == 60
    assert cell(out, "reference", "departures") == 6
    assert cell(out, "reference", "hazard") == 0.2
    kanon.check("departures", out, K)


def test_at_risk_below_k_takes_the_whole_row() -> None:
    out = tables.departures(periods([("placebo before", 4, 0, 0)]), K)
    row = out.row(0, named=True)
    assert [row[c] for c in ("at_risk", "departures", "record_ends", "hazard")] == [None] * 4


def test_record_ends_hidden_when_the_custodians_who_stayed_are_fewer_than_k() -> None:
    out = tables.departures(periods([("crisis", 20, 8, 9)]), K)  # 3 stayed
    assert cell(out, "crisis", "record_ends") is None
    assert cell(out, "crisis", "departures") == 8


def test_split_parts_are_published_only_together() -> None:
    before, after = schemas.DEPARTURE_SPLITS
    hidden = tables.departures(
        periods([("crisis", 60, 9, 0), (before, 60, 6, None), (after, 60, 3, None)]), K
    )
    assert cell(hidden, before, "departures") is None
    assert cell(hidden, after, "departures") is None
    assert cell(hidden, "crisis", "departures") == 9
    shown = tables.departures(
        periods([("crisis", 60, 11, 0), (before, 60, 6, None), (after, 60, 5, None)]), K
    )
    assert cell(shown, before, "departures") == 6
    assert cell(shown, after, "departures") == 5


def variant_rows(rows: list[tuple[str, int, int]]) -> pl.DataFrame:
    """(variant, smallest at risk, smallest cell) rows in contract shape."""
    return pl.DataFrame(
        [
            {
                "order": order,
                "variant": variant,
                "in_rule": True,
                "crisis_above_reference": True,
                "p": 0.01,
                "p_band": schemas.P_BANDS[1],
                "placebo_p": 0.5,
                "placebo_p_band": schemas.P_BANDS[2],
                "rolling_windows": 50,
                "above_rolling": True,
                "loo_stable": None,
                "outcome": None,
                "smallest_at_risk": at_risk,
                "smallest_cell": small,
                "placebo_smallest_cell": small,
            }
            for order, (variant, at_risk, small) in enumerate(rows, start=1)
        ],
        schema=schemas.table("departure_test_results").polars_schema,
    )


def test_p_published_only_for_the_primary_with_every_cell_at_least_k() -> None:
    out = tables.departure_tests(variant_rows([("primary", 30, 5), ("silence 8", 30, 9)]), K)
    assert out.columns == [c.name for c in schemas.table("departure_tests").cols]
    assert out.get_column("p").to_list() == [0.01, None]
    assert out.get_column("p_band").to_list() == [schemas.P_BANDS[1]] * 2
    small = tables.departure_tests(variant_rows([("primary", 30, 2)]), K)
    assert small.get_column("p").item() is None
    assert small.get_column("p_band").item() == schemas.P_BANDS[1]


def test_a_variant_with_fewer_than_k_at_risk_publishes_no_comparison() -> None:
    out = tables.departure_tests(variant_rows([("active 8", 3, 0)]), K)
    row = out.row(0, named=True)
    for column in ("crisis_above_reference", "p_band", "placebo_p_band", "above_rolling"):
        assert row[column] is None
