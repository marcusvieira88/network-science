"""`--set NAME=VALUE` overrides parse to each field's type; the manifest echoes every field."""

from __future__ import annotations

import pytest

from enron_case.config import Config
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
