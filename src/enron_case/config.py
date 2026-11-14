"""Single source of every pipeline parameter. Echoed in the run manifest.

Override at run time with `enron-case run --set NAME=VALUE`.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
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
# Where the master key comes from (contracts/cli.md). Fixed, not run parameters: the key
# location never enters the manifest, and the minimum length must not be lowered with --set.
KEY_ENV = "ENRON_CASE_KEY"
KEY_FILE_ENV = "ENRON_CASE_KEY_FILE"
DEFAULT_KEY_PATH = Path(".config") / "enron-case" / "key"  # relative to the home directory
MIN_KEY_BYTES = 32

# Percentile bootstrap interval (95%) of the risk scores, the utility effect and the
# within-custodian artifact check. The finding's block bootstrap uses `Config.ci_level`.
CI_PERCENTILES = (2.5, 97.5)

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
    # Ingest. Rows parsed before they are collected into a table (bounds memory), and the
    # corpus download's socket timeout.
    batch_rows: int = 50_000
    download_timeout_seconds: int = 60
    # Identity (research R4). An entity that sent more than `recipient_cap` recipients on at
    # least this many messages is a role mailbox; merges drawn for the manual review.
    role_min_mass_sends: int = 2
    manual_sample_size: int = 50
    # Finding: decision parameters fixed in docs/hypotheses.md before any real-data analysis.
    alpha: float = 0.05
    ci_level: float = 0.95
    block_weeks: int = 4
    min_after_weeks: int = 4
    min_baseline_weeks: int = 2
    # Rewired networks for the null model; each recomputes the whole series, which is costly.
    null_replicates: int = 20
    # Artifact checks (docs/hypotheses.md). A calm, out-of-sample half-year must not move the
    # metric by more than this many baseline standard deviations; a custodian enters the
    # within-person comparison with at least this many sent events in each period.
    placebo_max_effect: float = 2.0
    min_unit_events: int = 30
    # Exploratory families E1–E20 (docs/hypotheses-exploratory.md, fixed before computing).
    exploratory_min_messages: int = 20
    exploratory_bootstrap_reps: int = 2000
    # Subsamples per custodian when equalising mail volume between two windows (a check added
    # after E12 was computed: more mail kept means more chances to observe a reply).
    exploratory_equalise_reps: int = 40
    # Release mitigations. Lowest weighted degree of each published degree bucket; scale of the
    # Laplace noise in release R2 (a sketch, not a calibrated privacy budget; research R12).
    degree_bucket_floors: tuple[int, ...] = field(default=(1, 2, 5, 10))
    r2_noise_scale: float = 1.0
    # Risk (research R12). Custodians whose identity attacker A2 knows; (week, mapped person)
    # contacts an A2 guess needs in common; distance-matrix rows computed at once (memory).
    a2_seeds: int = 3
    a2_min_support: int = 2
    distance_chunk_rows: int = 1024

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


def _parse_like(example: object, raw: str, name: str) -> object:
    try:
        if isinstance(example, bool):
            return raw.lower() in {"1", "true", "yes"}
        if isinstance(example, int):
            return int(raw)
        if isinstance(example, float):
            return float(raw)
        if isinstance(example, date):
            return date.fromisoformat(raw)
        if isinstance(example, tuple):
            return _parse_tuple(example, raw)
    except ValueError as exc:
        raise UsageError(f"bad value for parameter {name}") from exc
    return raw


def _parse_tuple(example: tuple[object, ...], raw: str) -> tuple[object, ...]:
    """Comma-separated items, as integers when the default holds integers."""
    parts = tuple(part for part in raw.split(",") if part)
    if example and isinstance(example[0], int):
        return tuple(int(part) for part in parts)
    return parts


def _jsonable(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    return value
