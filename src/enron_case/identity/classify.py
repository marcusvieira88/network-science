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
     `config.role_min_mass_sends` messages.
   (No behavioural list rule: with ~150 collected mailboxes most real people never appear
   as a sender, so "never sends" says nothing about being a list.)
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

from enron_case.contracts.vocab import PERSON

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


@dataclass(frozen=True)
class Behaviour:
    """What an entity did as a sender; `role_min_mass_sends` (config.py) applies to it."""

    mass_sends: int


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
    """Per entity: messages it sent to more recipient addresses than the cap."""
    mass: dict[str, int] = defaultdict(int)
    for sender, recipients in messages.select("sender_addr", "recipients").iter_rows():
        sender_entity = entity_of.get(sender) if sender is not None else None
        if sender_entity is not None and len(recipients) > recipient_cap:
            mass[sender_entity] += 1
    return {e: Behaviour(mass_sends=mass[e]) for e in set(entity_of.values())}


def entity_type(addresses: Sequence[str], behaviour: Behaviour, role_min_mass_sends: int) -> str:
    """Type of one entity from its addresses (patterns) and behaviour, in documented order."""
    found = {pattern_type(addr.rsplit("@", 1)[0]) for addr in addresses if "@" in addr}
    for kind in (SYSTEM, ROLE, LIST):
        if kind in found:
            return kind
    if behaviour.mass_sends >= role_min_mass_sends:
        return ROLE
    return PERSON
