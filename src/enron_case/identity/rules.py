"""Identity evidence and merge rules N2-N5 with guards (T034, research R4).

Each rule emits `Candidate` merges between two nodes (normalised addresses, or legacy
directory strings for N4). A candidate with a `guard` set was blocked and is only counted.
`support` is the evidence count behind a candidate (distinct sends for N3 and N4; N2 needs no
count and records 1).
Rules are pure: tables in, candidates out. Union-find lives in `resolve.py`.

Evidence counting: a "send" is one distinct (address, timestamp) pair in `header_records`, so
the copies of one message in several mailboxes count once. Records without a timestamp cannot
be told apart from copies and are not counted (precision over recall).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations

import polars as pl

from enron_case.clean.addresses import clean_address
from enron_case.config import MULTI_LABEL_SUFFIXES
from enron_case.identity.classify import pattern_type

N2 = "N2"
N3 = "N3"
N4 = "N4"
RULE_ORDER = (N2, N3, N4)

GUARD_CROSS_ORG = "cross_org"
GUARD_GENERIC = "generic_local_part"
GUARD_NAME_ONLY = "name_only"
GUARD_AMBIGUOUS_LEGACY = "ambiguous_legacy"

ADDRESS_STRIP = " \t\"'<>;,."
MAILTO = "mailto:"
NAME_NOISE = re.compile(r"<[^>]*>|\([^)]*\)|[\"']")
WHITESPACE = re.compile(r"\s+")
ALPHA = re.compile(r"^[a-z]+$")
LIST_SEPARATOR = ","
LEGACY_MARK = "/"
REGISTERED_LABELS = 2
NAME_TOKENS = 2  # first.last


@dataclass(frozen=True, order=True)
class Candidate:
    left: str
    right: str
    rule: str
    support: int
    guard: str | None = None


# ---- N1 normalisation helpers ---------------------------------------------------------------
def normalize_address(raw: str) -> str:
    """Rule N1, single source in `clean.addresses` (no validity check here: callers look the
    result up in the set of addresses the clean stage already accepted)."""
    return clean_address(raw)


def normalize_name(raw: str | None) -> str | None:
    """Comparable display name: lower case, no quotes, brackets or comments, `Last, First`
    turned into `first last`. None when empty or when the name is itself an address."""
    if raw is None:
        return None
    value = NAME_NOISE.sub(" ", raw)
    if "@" in value:
        return None
    if value.count(",") == 1:
        last, first = value.split(",")
        value = f"{first} {last}"
    value = WHITESPACE.sub(" ", value).strip().lower()
    return value or None


def local_part(addr: str) -> str:
    return addr.rsplit("@", 1)[0]


def registered_domain(addr: str) -> str:
    """Registered domain: the last two labels, or three when the last two form a multi-label
    public suffix (`acme.co.uk`), so rule N2 never merges across companies under one suffix."""
    labels = addr.rsplit("@", 1)[-1].split(".")
    suffix = ".".join(labels[-REGISTERED_LABELS:])
    take = REGISTERED_LABELS + 1 if suffix in MULTI_LABEL_SUFFIXES else REGISTERED_LABELS
    return ".".join(labels[-take:])


def is_generic(addr: str) -> bool:
    return pattern_type(local_part(addr)) is not None


# ---- evidence -------------------------------------------------------------------------------
def address_occurrences(messages: pl.DataFrame) -> dict[str, int]:
    """Number of times each address appears in `messages`, as sender or as recipient."""
    counts: Counter[str] = Counter()
    for sender, recipients in messages.select("sender_addr", "recipients").iter_rows():
        if sender is not None:
            counts[sender] += 1
        counts.update(r["addr"] for r in recipients)
    return dict(counts)


def sender_name_support(headers: pl.DataFrame, known: set[str]) -> dict[tuple[str, str], int]:
    """Distinct sends per (normalised From address, normalised X-From name)."""
    seen: set[tuple[str, str, object]] = set()
    for addr_raw, name_raw, ts in headers.select("from_addr", "x_from", "ts_utc").iter_rows():
        if addr_raw is None or ts is None:
            continue
        addr, name = normalize_address(addr_raw), normalize_name(name_raw)
        if name is not None and addr in known:
            seen.add((addr, name, ts))
    return dict(Counter((addr, name) for addr, name, _ in seen))


# ---- N2 -------------------------------------------------------------------------------------
def subdomain_candidates(addresses: Iterable[str]) -> list[Candidate]:
    """N2: same local part under one registered domain (`x@sub.org.com` ~ `x@org.com`)."""
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for addr in sorted(set(addresses)):
        if "@" in addr:
            groups[(local_part(addr), registered_domain(addr))].append(addr)
    out = []
    for (local, _), members in sorted(groups.items()):
        guard = GUARD_GENERIC if pattern_type(local) is not None else None
        out += [Candidate(a, b, N2, 1, guard) for a, b in combinations(members, 2)]
    return out


# ---- N3 -------------------------------------------------------------------------------------
def compatible_local_parts(a: str, b: str) -> bool:
    """One is `first.last`, the other `flast`, `first_last` or `firstlast` of the same tokens."""
    return _alias_of_dotted(a, b) or _alias_of_dotted(b, a)


def _alias_of_dotted(dotted: str, other: str) -> bool:
    tokens = dotted.split(".")
    if len(tokens) != NAME_TOKENS or not all(ALPHA.match(t) for t in tokens):
        return False
    first, last = tokens
    return other in {first[0] + last, f"{first}_{last}", first + last}


def name_link_candidates(
    name_support: dict[tuple[str, str], int], min_support: int
) -> list[Candidate]:
    """N3: addresses sending under one display name, each at least `min_support` times."""
    by_name: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for (addr, name), n in sorted(name_support.items()):
        if n >= min_support:
            by_name[name].append((addr, n))
    out = []
    for _, members in sorted(by_name.items()):
        for (a, na), (b, nb) in combinations(members, 2):
            out.append(Candidate(a, b, N3, min(na, nb), _name_link_guard(a, b)))
    return out


def _name_link_guard(a: str, b: str) -> str | None:
    if registered_domain(a) != registered_domain(b):
        return GUARD_CROSS_ORG
    if is_generic(a) or is_generic(b):
        return GUARD_GENERIC
    if not compatible_local_parts(local_part(a), local_part(b)):
        return GUARD_NAME_ONLY
    return None


# ---- N4 -------------------------------------------------------------------------------------
def legacy_pairs(headers: pl.DataFrame, known: set[str]) -> dict[tuple[str, str], int]:
    """Distinct sends pairing a legacy directory string with the address at its position."""
    seen: set[tuple[str, str, object]] = set()
    rows = headers.select("ts_utc", "x_to", "to_addrs", "x_cc", "cc_addrs").iter_rows()
    for ts, x_to, to_addrs, x_cc, cc_addrs in rows:
        if ts is None:
            continue
        for names, addrs in ((x_to, to_addrs), (x_cc, cc_addrs)):
            for legacy, addr in _aligned_legacy(names, addrs):
                if addr in known:
                    seen.add((legacy, addr, ts))
    return dict(Counter((legacy, addr) for legacy, addr, _ in seen))


def _aligned_legacy(names: str | None, addrs: list[str]) -> list[tuple[str, str]]:
    if names is None:
        return []
    tokens = names.split(LIST_SEPARATOR)
    if len(tokens) != len(addrs):
        return []
    out = []
    for token, addr in zip(tokens, addrs, strict=True):
        if LEGACY_MARK in token and "@" not in token:
            out.append((WHITESPACE.sub(" ", token).strip().lower(), normalize_address(addr)))
    return out


def legacy_candidates(headers: pl.DataFrame, known: set[str], min_support: int) -> list[Candidate]:
    """N4: a legacy string paired with exactly one address at least `min_support` times.
    Paired that often with several addresses, it is ambiguous and blocked."""
    supported: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for (legacy, addr), n in sorted(legacy_pairs(headers, known).items()):
        if n >= min_support:
            supported[legacy].append((addr, n))
    out = []
    for legacy, matches in sorted(supported.items()):
        guard = GUARD_AMBIGUOUS_LEGACY if len(matches) > 1 else None
        out += [Candidate(legacy, addr, N4, n, guard) for addr, n in matches]
    return out


# ---- N5 -------------------------------------------------------------------------------------
def custodian_addresses(messages: pl.DataFrame) -> set[str]:
    """N5: per mailbox owner, the address that sent most of its sent-folder copies
    (ties go to the smallest address). Flags the entity; never merges."""
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for owner, sender in messages.select("sent_copy_owner", "sender_addr").iter_rows():
        if owner is not None and sender is not None:
            counts[owner][sender] += 1
    return {min(c, key=lambda a: (-c[a], a)) for c in counts.values()}


# ---- all rules ------------------------------------------------------------------------------
def evidence(messages: pl.DataFrame, headers: pl.DataFrame, min_support: int) -> list[Candidate]:
    """Candidates of rules N2, N3 and N4, in rule order."""
    known = set(address_occurrences(messages))
    return [
        *subdomain_candidates(known),
        *name_link_candidates(sender_name_support(headers, known), min_support),
        *legacy_candidates(headers, known, min_support),
    ]
