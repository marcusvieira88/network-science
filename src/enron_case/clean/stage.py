"""S2 clean: header_records -> messages and clean_counts (WP-B).

Logs counts only: never an address, an owner or a header value.
"""

from __future__ import annotations

from collections import Counter

import polars as pl

from enron_case.clean.dedupe import (
    Group,
    exact_pass,
    groups_from_records,
    pairwise_scores,
    subset_pass,
)
from enron_case.clean.noise import message_flags, message_id_shared_share
from enron_case.config import Config
from enron_case.context import StageContext
from enron_case.contracts import schemas
from enron_case.contracts import vocab as v
from enron_case.contracts.counts import CleanCounts


def run(ctx: StageContext) -> None:
    records = ctx.read("header_records")
    copies = groups_from_records(records)
    exact = exact_pass(copies)
    messages = subset_pass(exact)
    table = ctx.write("messages", messages_frame(messages, ctx.config))
    precision, recall = (None, None)
    if ctx.has_truth():
        truth = ctx.read_truth()["file_to_message"]
        by_file = {v.file_id(path): message for path, message in truth.items()}
        precision, recall = pairwise_scores((m.file_ids for m in messages), by_file)
    counts = clean_counts(
        records.height, len(exact), table, message_id_shared_share(exact), precision, recall
    )
    ctx.write_counts("clean_counts", dict(counts))
    ctx.log(
        f"clean: {counts['records_in']} records -> {counts['messages_out']} messages "
        f"(exact removed {counts['removed_exact']}, subset removed {counts['removed_subset']})"
    )


def messages_frame(messages: list[Group], config: Config) -> pl.DataFrame:
    """The `messages` table rows for merged groups."""
    rows = [
        {
            "msg_key": m.key,
            "ts_utc": m.ts_utc,
            "sender_addr": m.sender,
            "recipients": [{"addr": addr, "role": role} for addr, role in m.recipients],
            "n_recipients": len(m.recipients),
            "n_copies": m.n_copies,
            "dedupe_rule": m.rule,
            "owner_copies": sorted(m.owners),
            "sent_copy_owner": m.sent_owner,
            "flags": message_flags(m, config),
        }
        for m in messages
    ]
    return pl.DataFrame(rows, schema=schemas.table("messages").polars_schema)


def clean_counts(
    records_in: int,
    after_exact: int,
    messages: pl.DataFrame,
    message_id_share: float | None,
    precision: float | None,
    recall: float | None,
) -> CleanCounts:
    """Counts side output. Removed copies are counted per pass (records in minus groups after
    the exact pass; those minus messages after the subset pass), not by each message's final
    rule, which names only the last pass that touched it."""
    flags = Counter[str](messages.get_column("flags").explode().drop_nulls().to_list())
    return CleanCounts(
        records_in=records_in,
        messages_out=messages.height,
        removed_exact=records_in - after_exact,
        removed_subset=after_exact - messages.height,
        flags=dict(sorted(flags.items())),
        message_id_shared_share=message_id_share,
        dedupe_precision=precision,
        dedupe_recall=recall,
    )
