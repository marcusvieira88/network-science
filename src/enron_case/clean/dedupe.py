"""Deduplication without content (research R3): exact key pass, then subset pass.

A `Group` is one or more archive files judged to be the same message. Merging is pure and
deterministic: output depends on the set of input groups, not their order, and running it
again on its own output changes nothing.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from math import comb

import polars as pl

from enron_case.clean.addresses import normalize_address, resolve_recipients, strongest_role
from enron_case.contracts import vocab as v

SENT_FOLDER = "sent"
RULE_RANK = {rule: rank for rank, rule in enumerate(v.DEDUPE_RULES)}


@dataclass(frozen=True)
class Group:
    sender: str | None
    ts_utc: datetime | None
    recipients: tuple[tuple[str, str], ...]  # (addr, role), sorted by addr
    file_ids: frozenset[str]
    owners: frozenset[str]
    sent_owners: frozenset[str]
    message_ids: frozenset[str | None]
    bad_address: bool
    rule: str

    @classmethod
    def single(
        cls,
        *,
        file_id: str,
        owner: str,
        folder_class: str,
        sender: str | None,
        ts_utc: datetime | None,
        recipients: Mapping[str, str],
        message_id: str | None,
        bad_address: bool,
    ) -> Group:
        return cls(
            sender=sender,
            ts_utc=ts_utc,
            recipients=tuple(sorted(recipients.items())),
            file_ids=frozenset({file_id}),
            owners=frozenset({owner}),
            sent_owners=frozenset({owner}) if folder_class == SENT_FOLDER else frozenset(),
            message_ids=frozenset({message_id}),
            bad_address=bad_address,
            rule="none",
        )

    @property
    def addrs(self) -> frozenset[str]:
        return frozenset(addr for addr, _ in self.recipients)

    @property
    def key(self) -> str:
        return v.msg_key(self.sender, self.ts_utc, self.addrs)

    @property
    def n_copies(self) -> int:
        return len(self.file_ids)

    @property
    def sent_owner(self) -> str | None:
        return min(self.sent_owners, default=None)


def groups_from_records(records: pl.DataFrame) -> list[Group]:
    """One single-copy group per header record, with addresses normalised (rule N1)."""
    groups = []
    for row in records.iter_rows(named=True):
        recipients, bad = resolve_recipients(row["to_addrs"], row["cc_addrs"], row["bcc_addrs"])
        raw_sender = row["from_addr"]
        sender = normalize_address(raw_sender) if raw_sender is not None else None
        groups.append(
            Group.single(
                file_id=row["file_id"],
                owner=row["mailbox_owner"],
                folder_class=row["folder_class"],
                sender=sender,
                ts_utc=row["ts_utc"],
                recipients=recipients,
                message_id=row["message_id"],
                bad_address=bad or (raw_sender is not None and sender is None),
            )
        )
    return groups


def merge(members: list[Group], rule: str) -> Group:
    """Merge groups judged to be one message; the result keeps the strongest rule seen."""
    if len(members) == 1:
        return members[0]
    roles: dict[str, str] = {}
    for member in members:
        for addr, role in member.recipients:
            roles[addr] = strongest_role(roles.get(addr), role)
    first = members[0]
    return Group(
        sender=first.sender,
        ts_utc=first.ts_utc,
        recipients=tuple(sorted(roles.items())),
        file_ids=frozenset().union(*(m.file_ids for m in members)),
        owners=frozenset().union(*(m.owners for m in members)),
        sent_owners=frozenset().union(*(m.sent_owners for m in members)),
        message_ids=frozenset().union(*(m.message_ids for m in members)),
        bad_address=any(m.bad_address for m in members),
        rule=max([rule, *(m.rule for m in members)], key=RULE_RANK.__getitem__),
    )


def exact_pass(groups: Iterable[Group]) -> list[Group]:
    """Merge groups with the same message key (sender, second, recipient set).

    A record without a valid sender is never merged: with no sender, two unrelated messages
    in the same second to the same recipients would be indistinguishable."""
    buckets: dict[str, list[Group]] = defaultdict(list)
    for group in groups:
        bucket = group.key if group.sender is not None else f"{group.key}|{min(group.file_ids)}"
        buckets[bucket].append(group)
    merged = (merge(sorted(members, key=_order), "exact") for members in buckets.values())
    return sorted(merged, key=_order)


def subset_pass(groups: Iterable[Group]) -> list[Group]:
    """Within one sender and second, merge each recipient set into a superset holding it.

    Records without a timestamp or without a valid sender are left alone. A record without
    recipients (e.g. a Bcc-only recipient's copy) joins only when exactly one message is
    available to host it; an empty set is a subset of every set, so with two or more hosts it
    stays on its own rather than joining an unrelated message. A set contained in several
    incomparable supersets joins the largest one (ties broken by the sorted addresses), never
    more than one, so unrelated messages are not chained together.
    """
    buckets: dict[tuple[str | None, datetime], list[Group]] = defaultdict(list)
    out: list[Group] = []
    for group in groups:
        if group.ts_utc is None or group.sender is None:
            out.append(group)
        else:
            buckets[(group.sender, group.ts_utc.replace(microsecond=0))].append(group)
    for bucket in buckets.values():
        out.extend(_merge_subsets(bucket))
    return sorted(out, key=_order)


def _merge_subsets(bucket: list[Group]) -> list[Group]:
    maximal = [g for g in bucket if not any(g.addrs < other.addrs for other in bucket)]
    members: dict[str, list[Group]] = {g.key: [g] for g in maximal}
    for group in bucket:
        if group in maximal:
            continue
        hosts = [m for m in maximal if group.addrs < m.addrs]
        if not group.addrs and len(hosts) != 1:
            members[group.key] = [group]
            continue
        host = min(hosts, key=lambda m: (-len(m.addrs), sorted(m.addrs)))
        members[host.key].append(group)
    return [merge(sorted(found, key=_order), "subset") for found in members.values()]


def dedupe(groups: Iterable[Group]) -> list[Group]:
    """Exact pass then subset pass; output sorted by message key."""
    return subset_pass(exact_pass(groups))


def pairwise_scores(
    predicted: Iterable[frozenset[str]], truth: Mapping[str, str]
) -> tuple[float | None, float | None]:
    """Pairwise precision and recall of "same message" against ground truth.

    Both are None when there is no pair to score (no predicted or no true duplicate).
    """
    clusters = list(predicted)
    joint: dict[tuple[int, str], int] = defaultdict(int)
    true_sizes: dict[str, int] = defaultdict(int)
    for index, cluster in enumerate(clusters):
        for file_id in cluster:
            joint[(index, truth[file_id])] += 1
            true_sizes[truth[file_id]] += 1
    agreed = sum(comb(n, 2) for n in joint.values())
    predicted_pairs = sum(comb(len(c), 2) for c in clusters)
    true_pairs = sum(comb(n, 2) for n in true_sizes.values())
    precision = agreed / predicted_pairs if predicted_pairs else None
    recall = agreed / true_pairs if true_pairs else None
    return precision, recall


def _order(group: Group) -> tuple[str, list[str]]:
    return group.key, sorted(group.file_ids)
