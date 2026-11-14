"""T064: attacks re-identify planted unique nodes in R0 and nothing in aggregate releases; A2
grows from seeds; attack functions accept no truth; the scorer returns counts only."""

from __future__ import annotations

import dataclasses
import inspect
from datetime import date, timedelta

import polars as pl
import pytest

from enron_case.config import Config
from enron_case.risk import attack, score
from enron_case.risk.score import Score, score_guesses

WEEKS = [date(2001, 1, 1) + timedelta(days=7 * i) for i in range(6)]
CONFIG = Config()
FORBIDDEN = {"truth", "address_map", "key", "pid_of", "pid_of_address", "ctx"}


def r0_from(edges: list[tuple[int, str, str]], label: dict[str, str]) -> pl.DataFrame:
    """A node-level release (R0 shape) of a toy edge list, relabelled with pseudonyms."""
    return pl.DataFrame(
        {
            "week": [WEEKS[w] for w, _, _ in edges],
            "src_pid": [label[s] for _, s, _ in edges],
            "dst_pid": [label[d] for _, _, d in edges],
            "weight": [1.0] * len(edges),
        }
    )


def aux_from(edges: list[tuple[int, str, str]], address: dict[str, str]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "week": [WEEKS[w] for w, _, _ in edges],
            "src": [address[s] for _, s, _ in edges],
            "dst": [address[d] for _, _, d in edges],
        }
    )


# Five persons with distinct weekly patterns, so each is unique on its activity vector.
PERSONS = ["ann", "bob", "cat", "dan", "eve"]
PLANTED = [
    (0, "ann", "bob"),
    (0, "ann", "cat"),
    (1, "bob", "cat"),
    (2, "cat", "dan"),
    (2, "cat", "eve"),
    (2, "cat", "ann"),
    (3, "dan", "eve"),
    (4, "eve", "ann"),
    (4, "eve", "bob"),
    (5, "ann", "dan"),
]
PID = {p: f"p_{p}" for p in PERSONS}
ADDR = {p: f"{p}@example.org" for p in PERSONS}


def test_a1_reidentifies_planted_unique_nodes() -> None:
    guesses = attack.attack_a1(
        r0_from(PLANTED, PID), aux_from(PLANTED, ADDR), CONFIG.distance_chunk_rows
    )
    assert guesses == {PID[p]: ADDR[p] for p in PERSONS}


def test_a1_tolerates_extra_attacker_noise() -> None:
    # The attacker's archive also holds a mailing to everyone and an extra address.
    noisy = [*PLANTED, *((1, "news", p) for p in PERSONS)]
    guesses = attack.attack_a1(
        r0_from(PLANTED, PID),
        aux_from(noisy, {**ADDR, "news": "news@example.org"}),
        CONFIG.distance_chunk_rows,
    )
    assert guesses == {PID[p]: ADDR[p] for p in PERSONS}


def test_attacks_find_nothing_in_aggregate_release() -> None:
    aggregate = {"degree_distribution": pl.DataFrame({"persons": [5, 7]})}
    aux = aux_from(PLANTED, ADDR)
    assert attack.attack_a1(aggregate, aux, CONFIG.distance_chunk_rows) == {}
    assert attack.attack_a2(aggregate, aux, {PID["ann"]: ADDR["ann"]}, CONFIG.a2_min_support) == {}


def ring_with_chords(n: int) -> list[tuple[int, str, str]]:
    """A toy graph over n persons: each writes to the next two, in rotating weeks."""
    names = [f"n{i:02d}" for i in range(n)]
    return [(i % len(WEEKS), names[i], names[(i + step) % n]) for i in range(n) for step in (1, 2)]


def test_a2_propagates_from_seeds() -> None:
    edges = ring_with_chords(12)
    names = sorted({s for _, s, _ in edges})
    pid = {n: f"p_{n}" for n in names}
    addr = {n: f"{n}@example.org" for n in names}
    seeds = {pid[n]: addr[n] for n in names[:3]}
    guesses = attack.attack_a2(
        r0_from(edges, pid), aux_from(edges, addr), seeds, CONFIG.a2_min_support
    )
    assert not set(guesses) & set(seeds)  # seeds are prior knowledge, not guesses
    assert guesses == {pid[n]: addr[n] for n in names[3:]}


def test_a2_without_seeds_guesses_nothing() -> None:
    edges = ring_with_chords(12)
    names = sorted({s for _, s, _ in edges})
    release = r0_from(edges, {n: f"p_{n}" for n in names})
    assert (
        attack.attack_a2(release, aux_from(edges, {n: n for n in names}), {}, CONFIG.a2_min_support)
        == {}
    )


@pytest.mark.parametrize("function", [attack.attack_a1, attack.attack_a2])
def test_attack_signature_has_no_path_to_truth(function: object) -> None:
    assert callable(function)
    params = set(inspect.signature(function).parameters)
    assert params <= {"release", "aux_edges", "seeds", "chunk_rows", "min_support"}
    assert not params & FORBIDDEN


def test_score_matches_hand_count() -> None:
    truth = {"a@x": "p_1", "a2@x": "p_1", "b@x": "p_2", "c@x": "p_3"}
    guesses = {"p_1": "a2@x", "p_2": "b@x", "p_3": "a@x", "p_9": "a@x"}
    result = score_guesses(guesses, ["p_1", "p_2", "p_3", "p_4", "p_5"], truth, reps=200, seed=1)
    # p_1 right (alias of the same person), p_2 right, p_3 wrong, p_4 and p_5 unguessed.
    assert (result.n_targets, result.n_correct, result.rate) == (5, 2, 0.4)
    assert score_guesses(guesses, ["p_1", "p_2"], truth, reps=10, seed=1).rate == 1.0
    assert 0.0 <= result.ci_low <= result.rate <= result.ci_high <= 1.0


def test_score_with_no_guesses_is_zero() -> None:
    result = score_guesses({}, ["p_1", "p_2"], {"a@x": "p_1"}, reps=50, seed=1)
    assert (result.n_correct, result.rate, result.ci_low, result.ci_high) == (0, 0.0, 0.0, 0.0)


def test_scorer_returns_counts_only() -> None:
    fields = {f.name: f.type for f in dataclasses.fields(Score)}
    assert fields == {
        "n_targets": "int",
        "n_correct": "int",
        "rate": "float",
        "ci_low": "float",
        "ci_high": "float",
    }
    scorer = score.Scorer({"a@x": "p_1"}, {"a@x": 3}, reps=10, seed=1)
    assert isinstance(scorer.score({"p_1": "a@x"}, ["p_1"]), Score)


def test_seeds_are_best_supported_true_addresses() -> None:
    truth = {"a@x": "p_1", "a2@x": "p_1", "b@x": "p_2", "c@x": "p_3"}
    support = {"a@x": 2, "a2@x": 9, "b@x": 4, "c@x": 1}
    scorer = score.Scorer(truth, support, reps=10, seed=1)
    assert scorer.seeds({"p_1", "p_2", "p_3"}, 2) == {"p_1": "a2@x", "p_2": "b@x"}
