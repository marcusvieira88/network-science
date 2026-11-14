"""Entity typing (T035): person, list, system or role, from address patterns and behaviour.

Rules, applied in this order; the first that fires decides the type:

1. Pattern on any local part of the entity (`pattern_type`):
   - system: delivery and placeholder accounts (`mailer-daemon`, `postmaster`, `no.address`,
     `noreply`, `no-reply`, ...).
   - role: shared functional mailboxes (`announcements`, `info`, `admin`, `support`, `news`,
     `team`, `office`, ...), also as the last dot-separated token (`corp.announcements`).
   - list: distribution lists (`all.*`, `*.desk`, `*.list`, `*.group`, `dl.*`).
2. Behaviour (`entity_behaviour`):
   - role: sent more than `config.recipient_cap` recipients on at least
     `ROLE_MIN_MASS_SENDS` messages.
   - list: never sends and is addressed by at least `LIST_MIN_DISTINCT_SENDERS` distinct
     sender entities.
3. Otherwise person.

`unknown` is in the contract vocabulary but no rule assigns it: every resolved entity has at
least one well-formed address, which is enough to apply the rules above.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import polars as pl

PERSON = "person"
LIST = "list"
SYSTEM = "system"
ROLE = "role"

SYSTEM_LOCAL_PARTS = frozenset(
    {"mailer-daemon", "postmaster", "no.address", "noreply", "no-reply", "nobody", "root"}
)
ROLE_LOCAL_PARTS = frozenset(
    {
        "announcements",
        "announcement",
        "info",
        "admin",
        "administrator",
        "support",
        "help",
        "helpdesk",
        "news",
        "newsletter",
        "team",
        "office",
        "sales",
        "hr",
        "webmaster",
        "contact",
        "communications",
    }
)
LIST_PATTERN = re.compile(r"^(?:all|dl)[._-].+|.+[._-](?:desk|list|group)$")
TOKEN_SPLIT = re.compile(r"[._-]")

# Behaviour thresholds. "More than once" is the brief's definition of a role sender.
ROLE_MIN_MASS_SENDS = 2
# Not in config.py because the foundation is frozen for this work package; see the WP-C report.
LIST_MIN_DISTINCT_SENDERS = 10


@dataclass(frozen=True)
class Behaviour:
    sent: int
    mass_sends: int
    distinct_senders: int


def pattern_type(local: str) -> str | None:
    """Non-person type implied by a local part, or None when it looks like a person."""
    if local in SYSTEM_LOCAL_PARTS:
        return SYSTEM
    last_token = TOKEN_SPLIT.split(local)[-1]
    if local in ROLE_LOCAL_PARTS or last_token in {"announcements", "announcement"}:
        return ROLE
    if LIST_PATTERN.fullmatch(local):
        return LIST
    return None


def entity_behaviour(
    messages: pl.DataFrame, entity_of: Mapping[str, str], recipient_cap: int
) -> dict[str, Behaviour]:
    """Per entity: messages sent, messages sent above the cap, distinct sender entities."""
    sent: dict[str, int] = defaultdict(int)
    mass: dict[str, int] = defaultdict(int)
    senders: dict[str, set[str]] = defaultdict(set)
    for sender, recipients in messages.select("sender_addr", "recipients").iter_rows():
        sender_entity = entity_of.get(sender) if sender is not None else None
        if sender_entity is not None:
            sent[sender_entity] += 1
            if len(recipients) > recipient_cap:
                mass[sender_entity] += 1
        for recipient in recipients:
            target = entity_of.get(recipient["addr"])
            if target is not None and sender_entity is not None:
                senders[target].add(sender_entity)
    entities = set(entity_of.values())
    return {
        e: Behaviour(sent=sent[e], mass_sends=mass[e], distinct_senders=len(senders[e]))
        for e in entities
    }


def entity_type(addresses: Sequence[str], behaviour: Behaviour) -> str:
    """Type of one entity from its addresses (patterns) and behaviour, in documented order."""
    found = {pattern_type(addr.rsplit("@", 1)[0]) for addr in addresses if "@" in addr}
    for kind in (SYSTEM, ROLE, LIST):
        if kind in found:
            return kind
    if behaviour.mass_sends >= ROLE_MIN_MASS_SENDS:
        return ROLE
    if behaviour.sent == 0 and behaviour.distinct_senders >= LIST_MIN_DISTINCT_SENDERS:
        return LIST
    return PERSON
