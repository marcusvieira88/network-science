"""Plausible-date check. Out-of-range messages are flagged and kept, never dropped."""

from __future__ import annotations

from datetime import datetime

from enron_case.config import Config


def is_out_of_range(ts_utc: datetime | None, config: Config) -> bool:
    """True when the timestamp's UTC date lies outside the configured plausible range."""
    if ts_utc is None:
        return False
    day = ts_utc.date()
    return not config.plausible_start <= day <= config.plausible_end
