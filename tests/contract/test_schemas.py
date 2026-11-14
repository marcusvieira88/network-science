from __future__ import annotations

import polars as pl
import pytest

from enron_case.contracts import schemas
from enron_case.errors import ContractViolation
from enron_case.synth import SynthOutput


@pytest.mark.parametrize("name", sorted(schemas.TABLES))
def test_every_fixture_validates(synth: SynthOutput, name: str) -> None:
    schemas.validate(synth.table(name), name)


def test_extra_column_fails(synth: SynthOutput) -> None:
    df = synth.table("entities").with_columns(pl.lit("x").alias("display_name"))
    with pytest.raises(ContractViolation):
        schemas.validate(df, "entities")
    with pytest.raises(ContractViolation):
        schemas.conform(df, "entities")


def test_missing_column_fails(synth: SynthOutput) -> None:
    with pytest.raises(ContractViolation):
        schemas.conform(synth.table("entities").drop("type"), "entities")


def test_enum_violation_fails(synth: SynthOutput) -> None:
    df = synth.table("entities").with_columns(pl.lit("robot").alias("type"))
    with pytest.raises(ContractViolation):
        schemas.validate(df, "entities")


def test_pattern_violation_fails(synth: SynthOutput) -> None:
    df = synth.table("entities_p").with_columns(pl.lit("alice@example.com").alias("pid"))
    with pytest.raises(ContractViolation):
        schemas.validate(schemas.conform(df, "entities_p"), "entities_p")


def test_unsorted_fails(synth: SynthOutput) -> None:
    df = synth.table("messages").reverse()
    with pytest.raises(ContractViolation, match="not sorted"):
        schemas.validate(df, "messages")


def test_null_in_required_column_fails(synth: SynthOutput) -> None:
    df = synth.table("entities").with_columns(pl.lit(None, pl.Utf8).alias("org_domain"))
    with pytest.raises(ContractViolation):
        schemas.validate(df, "entities")


def test_release_tables_hold_no_identifiers(synth: SynthOutput) -> None:
    for name, spec in schemas.TABLES.items():
        if spec.zone.value == "release":
            assert schemas.leak_count(synth.table(name)) == 0, name


def test_leak_count_scans_every_element_of_a_list_cell() -> None:
    """Hand-counted: three list elements match an identifier pattern (an address, a person
    pseudonym and an organisation pseudonym); the clean elements, the empty list and the null
    cell count for nothing."""
    person = "p_" + "a" * 16
    org = "o_" + "b2" * 8
    df = pl.DataFrame(
        {
            "names": [
                ["clean", "someone@example.invalid"],
                [person, "also clean"],
                [org],
                [],
                None,
            ]
        },
        schema={"names": schemas.STR_LIST},
    )
    assert schemas.leak_count(df) == 3
    assert schemas.leak_count(df, ("@",)) == 1


def test_leak_count_passes_a_clean_list_column() -> None:
    # "p_short" is too short to be a pseudonym; "map_" is not followed by a 16-character body.
    df = pl.DataFrame(
        {"names": [["weekly", "p_short"], ["map_x"], []]},
        schema={"names": schemas.STR_LIST},
    )
    assert schemas.leak_count(df) == 0
