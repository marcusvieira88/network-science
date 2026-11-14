"""Re-identification attacks against a release variant (research R12).

Attack functions receive only a release and the attacker's auxiliary knowledge. They never see
the truth, the address map or the key; scoring is done separately in `risk/score.py`. Each
returns guesses as {pseudonym: address}.

A release is either a node-level weekly edge list (R0: `week, src_pid, dst_pid, weight`) or a
dict of aggregate tables (R1, R2), which contain no person-level record to attack.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from datetime import date

import numpy as np
import polars as pl

from enron_case.risk.features import (
    DST,
    N_IN,
    N_OUT,
    NODE,
    SRC,
    WEEK,
    weekly_activity,
    weekly_contacts,
)

Release = pl.DataFrame | dict[str, pl.DataFrame]

# Release-side column names of the node-level edge list (release.variants.build_r0).
RELEASE_SRC = "src_pid"
RELEASE_DST = "dst_pid"
# Rows of the distance matrix computed at once; bounds memory on the full corpus.
DISTANCE_CHUNK = 1024
# A2: a guess needs at least this many (week, mapped person) contacts in common.
A2_MIN_SUPPORT = 2


def person_edges(release: Release) -> pl.DataFrame | None:
    """The release's node-level edges as `(week, src, dst)`, or None for an aggregate release."""
    if not isinstance(release, pl.DataFrame):
        return None
    return node_edges(release)


def node_edges(release: pl.DataFrame) -> pl.DataFrame:
    """A node-level release's edges renamed to `(week, src, dst)`."""
    return release.select(WEEK, pl.col(RELEASE_SRC).alias(SRC), pl.col(RELEASE_DST).alias(DST))


def attack_a1(release: Release, aux_edges: pl.DataFrame) -> dict[str, str]:
    """Outsider: match each pseudonym to the address with the nearest weekly activity vector
    (distinct persons written to and heard from, per week)."""
    edges = person_edges(release)
    if edges is None:
        return {}
    released, observed = weekly_activity(edges), weekly_activity(aux_edges)
    weeks = sorted(set(released.get_column(WEEK)) | set(observed.get_column(WEEK)))
    pids = sorted(set(released.get_column(NODE)))
    addresses = sorted(set(observed.get_column(NODE)))
    if not pids or not addresses:
        return {}
    best = nearest_rows(
        activity_matrix(released, pids, weeks), activity_matrix(observed, addresses, weeks)
    )
    return {pid: addresses[i] for pid, i in zip(pids, best, strict=True)}


def activity_matrix(activity: pl.DataFrame, nodes: list[str], weeks: list[date]) -> np.ndarray:
    """Rows = nodes, columns = (weeks × sent) followed by (weeks × received)."""
    row = {n: i for i, n in enumerate(nodes)}
    col = {w: j for j, w in enumerate(weeks)}
    matrix = np.zeros((len(nodes), 2 * len(weeks)), dtype=np.float32)
    for node, week, n_out, n_in in activity.select(NODE, WEEK, N_OUT, N_IN).iter_rows():
        matrix[row[node], col[week]] = n_out
        matrix[row[node], len(weeks) + col[week]] = n_in
    return matrix


def nearest_rows(queries: np.ndarray, candidates: np.ndarray) -> list[int]:
    """Index of the Euclidean-nearest candidate for each query row (first index on ties)."""
    candidate_norms = np.sum(candidates.astype(np.float64) ** 2, axis=1)
    best: list[int] = []
    for start in range(0, queries.shape[0], DISTANCE_CHUNK):
        block = queries[start : start + DISTANCE_CHUNK].astype(np.float64)
        distances = candidate_norms[None, :] - 2.0 * (block @ candidates.T.astype(np.float64))
        best.extend(int(i) for i in np.argmin(distances, axis=1))
    return best


def attack_a2(
    release: Release, aux_edges: pl.DataFrame, seeds: Mapping[str, str]
) -> dict[str, str]:
    """Insider: start from known seed identities and propagate through the release graph.
    A pseudonym is mapped to the address whose weekly contacts with already-mapped persons
    best match its own; each round's matches become evidence for the next.

    Returns new guesses only; the seeds themselves are not guesses.
    """
    edges = person_edges(release)
    if edges is None:
        return {}
    released, observed = weekly_contacts(edges), weekly_contacts(aux_edges)
    mapping = {p: a for p, a in seeds.items() if p in released and a in observed}
    while True:
        accepted = accept(propose(released, observed, mapping))
        if not accepted:
            break
        mapping.update(accepted)
    return {p: a for p, a in sorted(mapping.items()) if p not in seeds}


Contacts = dict[str, set[tuple[date, str]]]


def propose(
    released: Contacts, observed: Contacts, mapping: dict[str, str]
) -> dict[str, tuple[str, float]]:
    """For each unmapped pseudonym, its single best-scoring unused address, if unambiguous.

    Support = (week, mapped person) contacts the two share. Score = support / sqrt(address
    contacts), so busy addresses do not win by size alone.
    """
    used = set(mapping.values())
    proposals: dict[str, tuple[str, float]] = {}
    for pid in sorted(set(released) - set(mapping)):
        support = Counter(
            address
            for week, neighbour in released[pid]
            if neighbour in mapping
            for contact_week, address in observed[mapping[neighbour]]
            if contact_week == week and address not in used
        )
        ranked = sorted(
            (
                (n / math.sqrt(len(observed[a])), a)
                for a, n in support.items()
                if n >= A2_MIN_SUPPORT
            ),
            reverse=True,
        )
        if ranked and (len(ranked) == 1 or ranked[0][0] > ranked[1][0]):
            proposals[pid] = (ranked[0][1], ranked[0][0])
    return proposals


def accept(proposals: dict[str, tuple[str, float]]) -> dict[str, str]:
    """Keep each address for the pseudonym that proposes it with the strictly highest score."""
    by_address: dict[str, list[tuple[float, str]]] = {}
    for pid, (address, score) in proposals.items():
        by_address.setdefault(address, []).append((score, pid))
    accepted: dict[str, str] = {}
    for address, bids in by_address.items():
        bids.sort(reverse=True)
        if len(bids) == 1 or bids[0][0] > bids[1][0]:
            accepted[bids[0][1]] = address
    return accepted
