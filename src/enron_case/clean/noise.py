"""Message noise flags and the research R3 Message-ID diagnostic."""

from __future__ import annotations

from collections.abc import Iterable

from enron_case.clean.dates import is_out_of_range
from enron_case.clean.dedupe import Group
from enron_case.config import Config


def message_flags(group: Group, config: Config) -> list[str]:
    """Sorted noise flags of one merged message. Flagged messages are kept, not dropped."""
    addrs = group.addrs
    checks = {
        "bad_address": group.bad_address,
        "date_out_of_range": is_out_of_range(group.ts_utc, config),
        "mass_mailing": len(addrs) > config.recipient_cap,
        "no_recipients": not addrs,
        "self_only": group.sender is not None and addrs == {group.sender},
    }
    return sorted(flag for flag, raised in checks.items() if raised)


def message_id_shared_share(exact_groups: Iterable[Group]) -> float | None:
    """Share of exact-duplicate groups (two or more copies) whose copies all carry one
    Message-ID. None when there is no exact-duplicate group."""
    duplicates = [g for g in exact_groups if g.n_copies > 1]
    if not duplicates:
        return None
    shared = sum(1 for g in duplicates if len(g.message_ids) == 1 and None not in g.message_ids)
    return shared / len(duplicates)
