"""`--set NAME=VALUE` overrides parse to each field's type; the manifest echoes every field."""

from __future__ import annotations

from datetime import date

import pytest

from enron_case.config import Config, _parse_like
from enron_case.errors import UsageError


def test_float_override_parses_to_float() -> None:
    assert Config().with_overrides({"alpha": "0.01"}).alpha == 0.01


def test_integer_tuple_override_parses_to_integers() -> None:
    config = Config().with_overrides({"degree_bucket_floors": "1,3,10"})
    assert config.degree_bucket_floors == (1, 3, 10)


def test_string_tuple_override_stays_strings() -> None:
    config = Config().with_overrides({"sensitivity_variants": "cap=20"})
    assert config.sensitivity_variants == ("cap=20",)


def test_bad_float_is_a_usage_error() -> None:
    with pytest.raises(UsageError):
        Config().with_overrides({"r2_noise_scale": "high"})


def test_manifest_record_echoes_tunable_parameters() -> None:
    record = Config().as_record()
    assert record["placebo_max_effect"] == 2.0
    assert record["degree_bucket_floors"] == [1, 2, 5, 10]
    assert record["null_replicates"] == 20


def test_integer_date_and_string_overrides_parse_to_their_field_types() -> None:
    config = Config().with_overrides(
        {"k_min": "7", "plausible_start": "1999-02-03", "window": "month"}
    )
    assert config.k_min == 7
    assert config.plausible_start == date(1999, 2, 3)
    assert config.window == "month"


def test_bad_integer_and_bad_date_are_usage_errors() -> None:
    with pytest.raises(UsageError, match="bad value for parameter k_min"):
        Config().with_overrides({"k_min": "five"})
    with pytest.raises(UsageError, match="bad value for parameter plausible_end"):
        Config().with_overrides({"plausible_end": "2002-13-01"})


def test_unknown_parameter_is_a_usage_error() -> None:
    with pytest.raises(UsageError, match="unknown parameter: k_maximum"):
        Config().with_overrides({"k_maximum": "3"})


def test_boolean_values_parse_from_the_documented_spellings() -> None:
    """No Config field is a bool today; the rule is checked on the parser itself because a bool
    is also an int and must be matched first."""
    assert [_parse_like(False, raw, "flag") for raw in ("1", "TRUE", "yes", "0", "no")] == [
        True,
        True,
        True,
        False,
        False,
    ]
