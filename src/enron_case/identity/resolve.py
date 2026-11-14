"""Deterministic union-find over identity candidates (T036).

- Accepted candidates are applied in rule order (N2, N3, N4), then in sorted order, so the
  result does not depend on input order.
- `entity_id` is the lexicographically smallest normalised address in the cluster (legacy
  directory strings never become canonical).
- Each attached address records the rule of the merge edge through which it is first reached
  from the canonical address (breadth-first over the merge tree, neighbours in sorted order).
- `support` is the number of message occurrences of an address (sender or recipient); for a
  legacy string, which never occurs in `messages`, it is the N4 pairing count.
- Blocked candidates are counted once per distinct pair of final clusters and guard.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import polars as pl

from enron_case.contracts import schemas
from enron_case.identity.rules import RULE_ORDER, Candidate


@dataclass(frozen=True)
class Resolution:
    address_map: pl.DataFrame
    blocked_by_guard: dict[str, int]


class UnionFind:
    def __init__(self, nodes: Sequence[str]) -> None:
        self.parent = {n: n for n in nodes}

    def find(self, node: str) -> str:
        root = node
        while self.parent.get(root, root) != root:
            root = self.parent[root]
        while node != root:
            self.parent[node], node = root, self.parent[node]
        return root

    def union(self, a: str, b: str) -> bool:
        """Join the clusters of a and b; False when they were already one."""
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        low, high = sorted((ra, rb))
        self.parent[high] = low
        return True


def resolve(occurrences: Mapping[str, int], candidates: Sequence[Candidate]) -> Resolution:
    """Cluster the observed addresses with the accepted candidates; see module docstring."""
    ordered = sorted(candidates, key=lambda c: (RULE_ORDER.index(c.rule), c))
    accepted = [c for c in ordered if c.guard is None]
    support = dict(occurrences)
    for c in accepted:
        for node in (c.left, c.right):
            support.setdefault(node, c.support)
    forest = UnionFind(sorted(support))
    tree: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for c in accepted:
        if forest.union(c.left, c.right):
            tree[c.left].append((c.right, c.rule))
            tree[c.right].append((c.left, c.rule))

    members: dict[str, list[str]] = defaultdict(list)
    for node in sorted(support):
        members[forest.find(node)].append(node)
    rows = []
    for cluster in members.values():
        canonical = min(n for n in cluster if "@" in n)
        for node, rule in _attachment_rules(canonical, tree).items():
            rows.append(
                {"addr": node, "entity_id": canonical, "rule": rule, "support": support[node]}
            )
    amap = schemas.conform(
        pl.DataFrame(rows, schema=schemas.table("address_map").polars_schema), "address_map"
    )
    return Resolution(amap, _blocked(ordered, forest))


def _attachment_rules(
    canonical: str, tree: Mapping[str, list[tuple[str, str]]]
) -> dict[str, str | None]:
    rules: dict[str, str | None] = {canonical: None}
    queue = deque([canonical])
    while queue:
        node = queue.popleft()
        for neighbour, rule in sorted(tree.get(node, [])):
            if neighbour not in rules:
                rules[neighbour] = rule
                queue.append(neighbour)
    return rules


def _blocked(candidates: Sequence[Candidate], forest: UnionFind) -> dict[str, int]:
    pairs = {
        (c.guard, *sorted((forest.find(c.left), forest.find(c.right))))
        for c in candidates
        if c.guard is not None and forest.find(c.left) != forest.find(c.right)
    }
    return dict(sorted(Counter(guard for guard, _, _ in pairs).items()))
