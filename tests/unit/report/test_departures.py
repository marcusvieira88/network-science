"""H26 report sentences (report/departures.py) from release-shaped tables."""

from __future__ import annotations

import polars as pl

from enron_case.config import Config
from enron_case.release import tables as release_tables
from enron_case.report import departures
from enron_case.synth import SynthOutput

CONFIG = Config()


def released(synth: SynthOutput) -> tuple[pl.DataFrame, pl.DataFrame]:
    return synth.table("departures"), synth.table("departure_tests")


def test_a_held_finding_states_its_numbers_and_confidence(synth: SynthOutput) -> None:
    periods, tests = released(synth)
    text = departures.departure_statement(periods, tests, CONFIG)
    assert "12 of 40 at risk (share 0.3) in the crisis window" in text
    assert "Confidence: moderate." in text
    assert "7 began before 2001-10-16" in text
    assert departures.departure_summary(tests).endswith("confidence: moderate.")
    assert "would have needed at least 7 departures of 40 at risk" in text


def test_nothing_established_names_the_failed_conditions(synth: SynthOutput) -> None:
    periods = synth.table("departures").with_columns(
        pl.when(pl.col("period") != "reference").then(3).otherwise(2).alias("departures")
    )
    restricted = periods.with_columns((pl.col("departures") / pl.col("at_risk")).alias("hazard"))
    published = release_tables.departures(restricted, CONFIG.k_min)
    tests = synth.table("departure_tests").with_columns(
        pl.lit("not established").alias("outcome"),
        pl.lit("alpha or above").alias("p_band"),
        pl.lit(None, dtype=pl.Float64).alias("p"),
        pl.lit(False).alias("above_rolling"),
    )
    text = departures.departure_statement(published, tests, CONFIG)
    assert "fewer than 5 of 40 at risk in the crisis window" in text
    assert "No departure wave can be established: fewer than 5 custodians departed" in text
    assert "(p 0.05 or above)" in text
    assert "an earlier window of the same length had at least as high a share" in text
    assert "neither is published" in text
    assert "leave-one-out does not apply" in text
    assert departures.departure_summary(tests).startswith("No wave")
