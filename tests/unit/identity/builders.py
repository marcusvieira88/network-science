"""Hand-built `messages` and `header_records` rows for identity tests (invented addresses)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl

from enron_case.contracts import schemas

BASE = datetime(2001, 1, 1, tzinfo=UTC)


def messages(rows: list[tuple[str, list[str]]], sent_owner: dict[int, str] | None = None) -> pl.DataFrame:
    """One message per (sender, recipients); `sent_owner` maps a row index to the owner whose
    sent folder held it."""
    owners = sent_owner or {}
    data = [
        {
            "msg_key": f"{i:020x}",
            "ts_utc": BASE + timedelta(hours=i),
            "sender_addr": sender,
            "recipients": [{"addr": r, "role": "to"} for r in recipients],
            "n_recipients": len(recipients),
            "n_copies": 1,
            "dedupe_rule": "none",
            "owner_copies": [],
            "sent_copy_owner": owners.get(i),
            "flags": [],
        }
        for i, (sender, recipients) in enumerate(rows)
    ]
    return schemas.conform(pl.DataFrame(data, schema=schemas.table("messages").polars_schema), "messages")


def headers(rows: list[dict[str, object]]) -> pl.DataFrame:
    """Header records; each row gives from_addr, x_from and optionally to_addrs/x_to, cc_addrs/x_cc."""
    data = []
    for i, row in enumerate(rows):
        data.append(
            {
                "file_id": f"{i:016x}",
                "mailbox_owner": "owner-a",
                "folder_class": "inbox",
                "date_raw_ok": True,
                "ts_utc": BASE + timedelta(hours=i),
                "from_addr": row.get("from_addr"),
                "to_addrs": row.get("to_addrs", []),
                "cc_addrs": row.get("cc_addrs", []),
                "bcc_addrs": [],
                "x_from": row.get("x_from"),
                "x_to": row.get("x_to"),
                "x_cc": row.get("x_cc"),
                "x_bcc": None,
                "message_id": None,
                "parse_flags": [],
            }
        )
    return schemas.conform(
        pl.DataFrame(data, schema=schemas.table("header_records").polars_schema), "header_records"
    )


def sends(addr: str, name: str, times: int) -> list[dict[str, object]]:
    return [{"from_addr": addr, "x_from": name, "to_addrs": ["peer@org.com"]} for _ in range(times)]
