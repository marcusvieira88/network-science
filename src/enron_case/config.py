"""Single source of every pipeline parameter. Echoed in the run manifest.

Override at run time with `enron-case run --set NAME=VALUE`.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from enron_case.errors import UsageError

CORPUS_URL = "https://www.cs.cmu.edu/~enron/enron_mail_20150507.tar.gz"
CORPUS_ARCHIVE = "enron_mail_20150507.tar.gz"
# SHA-256 of the archive above; pinned after the first verified download.
CORPUS_SHA256 = "b3da1b3fe0369ec3140bb4fbce94702c33b7da810ec15d718b3fadf5cd748ca7"
SAMPLE_ARCHIVE = "synthetic_maildir.tar.gz"
# Fixed key for the synthetic sample and tests only. `--sample` always uses it, so the real key
# never touches synthetic data and synthetic runs never need the real key.
SAMPLE_KEY_HEX = "7465737400000000000000000000000000000000000000000000000000000000"

INTERNAL_DOMAIN = "enron.com"
# Two-label public suffixes; under these the registered domain takes three labels.
MULTI_LABEL_SUFFIXES = frozenset(
    {
        "co.uk",
        "org.uk",
        "ac.uk",
        "gov.uk",
        "com.au",
        "net.au",
        "org.au",
        "co.jp",
        "co.nz",
        "com.br",
        "com.mx",
        "co.za",
        "com.sg",
        "com.hk",
        "co.in",
        "com.cn",
        "co.kr",
        "com.ar",
    }
)
SAMPLE_INTERNAL_DOMAIN = "acme-energy.com"

# Public events, used only to annotate series. Never used to choose windows.
PUBLIC_EVENTS: tuple[tuple[date, str], ...] = (
    (date(2001, 8, 14), "CEO resignation announced"),
    (date(2001, 10, 16), "Third-quarter loss announced"),
    (date(2001, 10, 22), "SEC inquiry disclosed"),
    (date(2001, 11, 8), "Earnings restatement"),
    (date(2001, 12, 2), "Chapter 11 filing"),
)


@dataclass(frozen=True)
class Config:
    seed: int = 20011202
    k_min: int = 5
    window: str = "week"  # "week" or "month"
    recipient_cap: int = 50
    plausible_start: date = date(1998, 1, 1)
    plausible_end: date = date(2002, 12, 31)
    analysis_start: date = date(2000, 1, 1)
    analysis_end: date = date(2002, 3, 31)
    baseline_start: date = date(2000, 1, 1)
    baseline_end: date = date(2000, 12, 31)
    name_link_support: int = 3
    bootstrap_reps: int = 1000
    permutations: int = 1000
    ts_resolution: str = "hour"
    internal_domain: str = INTERNAL_DOMAIN
    sensitivity_variants: tuple[str, ...] = field(default=("cap=20", "window=month"))

    def with_overrides(self, overrides: dict[str, str]) -> Config:
        """Return a copy with string overrides parsed to each field's type."""
        current = dataclasses.asdict(self)
        updates: dict[str, Any] = {}
        for name, raw in overrides.items():
            if name not in current:
                raise UsageError(f"unknown parameter: {name}")
            updates[name] = _parse_like(current[name], raw, name)
        return dataclasses.replace(self, **updates)

    def as_record(self) -> dict[str, Any]:
        """JSON-serialisable view for the run manifest."""
        return {k: _jsonable(v) for k, v in dataclasses.asdict(self).items()}


def _parse_like(example: Any, raw: str, name: str) -> Any:
    try:
        if isinstance(example, bool):
            return raw.lower() in {"1", "true", "yes"}
        if isinstance(example, int):
            return int(raw)
        if isinstance(example, date):
            return date.fromisoformat(raw)
        if isinstance(example, tuple):
            return tuple(part for part in raw.split(",") if part)
    except ValueError as exc:
        raise UsageError(f"bad value for parameter {name}") from exc
    return raw


def _jsonable(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    return value
