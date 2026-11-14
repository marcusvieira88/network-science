"""Plausible-date check (T026)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from enron_case.clean.dates import is_out_of_range
from enron_case.config import Config

CONFIG = Config()


@pytest.mark.parametrize(
    ("ts", "expected"),
    [
        (datetime(2001, 6, 1, 12, 0, tzinfo=UTC), False),
        (datetime(1998, 1, 1, 0, 0, tzinfo=UTC), False),
        (datetime(2002, 12, 31, 23, 59, 59, tzinfo=UTC), False),
        (datetime(1997, 12, 31, 23, 59, 59, tzinfo=UTC), True),
        (datetime(2003, 1, 1, 0, 0, tzinfo=UTC), True),
        (datetime(1980, 3, 1, 9, 0, tzinfo=UTC), True),
        (None, False),
    ],
)
def test_out_of_range(ts: datetime | None, expected: bool) -> None:
    assert is_out_of_range(ts, CONFIG) is expected


def test_range_follows_config() -> None:
    narrow = Config(plausible_start=date(2001, 1, 1), plausible_end=date(2001, 12, 31))
    assert is_out_of_range(datetime(2000, 6, 1, tzinfo=UTC), narrow)
    assert not is_out_of_range(datetime(2001, 6, 1, tzinfo=UTC), narrow)
