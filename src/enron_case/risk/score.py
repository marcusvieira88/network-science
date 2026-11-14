"""Scoring attacker guesses against the truth (research R12).

This is the only risk module that reads the ingest zone or loads the key. It resolves a guessed
address to the pseudonym our pipeline gave that person (via `address_map` and the keyed
pseudonym function it builds) and reports counts and rates only. No identity and no key leaves
this module except the seed identities attacker A2 is defined to know.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from enron_case.config import CI_PERCENTILES
from enron_case.context import StageContext
from enron_case.errors import PipelineError

# Interval bounds of the percentile bootstrap.

PidOf = Callable[[str], str]


def keyed_pid_of() -> PidOf:
    """The pipeline's person pseudonym function (WP-D `person_pid`) bound to the run key. The
    key stays inside the returned closure."""
    keys: Any = importlib.import_module("enron_case.pseudo.keys")
    pseudonymize: Any = importlib.import_module("enron_case.pseudo.pseudonymize")
    key: bytes = keys.load_key()

    def pid_of(entity_id: str) -> str:
        pid: str = pseudonymize.person_pid(key, entity_id)
        return pid

    return pid_of


@dataclass(frozen=True)
class Score:
    n_targets: int
    n_correct: int
    rate: float
    ci_low: float
    ci_high: float


def score_guesses(
    guesses: Mapping[str, str],
    targets: Collection[str],
    pid_of_address: Mapping[str, str],
    reps: int,
    seed: int,
) -> Score:
    """Top-1 re-identification rate over `targets` with a percentile bootstrap interval.

    A guess is correct when the guessed address belongs to the person behind the pseudonym.
    Targets without a guess count as not re-identified; guesses for non-targets are ignored.
    """
    if not targets:
        raise PipelineError("no persons in scope to score")
    hits = np.array(
        [pid_of_address.get(guesses.get(pid, "")) == pid for pid in sorted(targets)],
        dtype=np.float64,
    )
    rng = np.random.default_rng(seed)
    resampled = rng.choice(hits, size=(reps, hits.size), replace=True).mean(axis=1)
    return Score(
        n_targets=int(hits.size),
        n_correct=int(hits.sum()),
        rate=float(hits.mean()),
        ci_low=float(np.percentile(resampled, CI_PERCENTILES[0])),
        ci_high=float(np.percentile(resampled, CI_PERCENTILES[1])),
    )


class Scorer:
    """Holds the address → pseudonym truth privately; hands out scores only."""

    def __init__(
        self, pid_of_address: dict[str, str], support: dict[str, int], reps: int, seed: int
    ) -> None:
        self._pid_of_address = pid_of_address
        self._support = support
        self._reps = reps
        self._seed = seed

    @classmethod
    def from_context(cls, ctx: StageContext, pid_of: PidOf | None = None) -> Scorer:
        """Build from the ingest-zone address map. Entity ids map to pseudonyms through the
        keyed function built here, or through `pid_of` when a test injects one (the synthetic
        fixtures use their own pseudonym function)."""
        if pid_of is None:
            pid_of = keyed_pid_of()
        amap = ctx.read("address_map")
        entity_pid = {e: pid_of(e) for e in amap.get_column("entity_id").unique().to_list()}
        pid_of_address: dict[str, str] = {}
        support: dict[str, int] = {}
        for addr, entity_id, n in amap.select("addr", "entity_id", "support").iter_rows():
            pid_of_address[addr] = entity_pid[entity_id]
            support[addr] = n
        return cls(pid_of_address, support, ctx.config.bootstrap_reps, ctx.config.seed)

    def score(self, guesses: Mapping[str, str], targets: Collection[str]) -> Score:
        return score_guesses(guesses, targets, self._pid_of_address, self._reps, self._seed)

    def seeds(self, candidates: Collection[str], n: int) -> dict[str, str]:
        """A2's prior knowledge: the true, best-supported address of the first `n` candidate
        pseudonyms (in sorted order) that have one."""
        best: dict[str, tuple[int, str]] = {}
        for addr, pid in self._pid_of_address.items():
            ranked = (self._support[addr], addr)
            if pid in candidates and (pid not in best or ranked > best[pid]):
                best[pid] = ranked
        return {pid: best[pid][1] for pid in sorted(best)[:n]}
