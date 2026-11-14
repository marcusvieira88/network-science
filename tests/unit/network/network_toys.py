"""Hand-built events and entities for network tests. Every value is invented."""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

import polars as pl

from enron_case.config import Config
from enron_case.contracts import schemas
from enron_case.contracts import vocab as v

WEEK_1 = date(2000, 3, 6)  # a Monday
WEEK_2 = WEEK_1 + timedelta(days=7)
WEEK_3 = WEEK_1 + timedelta(days=14)


def pid(label: str) -> str:
    return v.format_pseudonym(v.PERSON_PREFIX, hashlib.sha256(label.encode()).digest())


def org(label: str) -> str:
    return v.format_pseudonym(v.ORG_PREFIX, hashlib.sha256(label.encode()).digest())


def toy_config(weeks: int = 2, k_min: int = 5) -> Config:
    """Analysis and baseline window covering `weeks` weeks from WEEK_1."""
    end = WEEK_1 + timedelta(days=7 * weeks - 1)
    return dataclasses.replace(
        Config(),
        k_min=k_min,
        analysis_start=WEEK_1,
        analysis_end=end,
        baseline_start=WEEK_1,
        baseline_end=end,
    )


@dataclasses.dataclass(frozen=True)
class Person:
    label: str
    internal: bool = True
    custodian: bool = False
    type: str = "person"

    @property
    def pid(self) -> str:
        return pid(self.label)


class Mailbag:
    """Collects messages and renders them as an `events` table (one row per recipient)."""

    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []
        self.count = 0

    def send(
        self,
        sender: Person,
        recipients: Iterable[Person],
        week: date = WEEK_1,
        in_network: bool = True,
        n_recipients: int | None = None,
    ) -> None:
        recipients = list(recipients)
        n = n_recipients if n_recipients is not None else len(recipients)
        self.count += 1
        msg = f"msg{self.count}"
        ts = datetime(week.year, week.month, week.day, 10, tzinfo=UTC) + timedelta(days=1)
        for r in recipients:
            self.rows.append(
                {
                    "event_id": v.format_pseudonym(
                        v.EVENT_PREFIX, hashlib.sha256(f"{msg}|{r.label}".encode()).digest()
                    ),
                    "msg_pid": v.format_pseudonym(
                        v.MESSAGE_PREFIX, hashlib.sha256(msg.encode()).digest()
                    ),
                    "ts_hour": ts,
                    "sender_pid": sender.pid,
                    "recipient_pid": r.pid,
                    "role": "to",
                    "n_recipients": n,
                    "weight": 1.0 / n,
                    "sender_type": sender.type,
                    "recipient_type": r.type,
                    "sender_internal": sender.internal,
                    "recipient_internal": r.internal,
                    "sender_org_pid": org("inside" if sender.internal else "outside"),
                    "recipient_org_pid": org("inside" if r.internal else "outside"),
                    "in_network": in_network,
                }
            )

    def events(self) -> pl.DataFrame:
        frame = pl.DataFrame(self.rows, schema=schemas.table("events").polars_schema)
        return schemas.conform(frame, "events")


def entities(people: Iterable[Person]) -> pl.DataFrame:
    rows = [
        {
            "pid": p.pid,
            "type": p.type,
            "org_pid": org("inside" if p.internal else "outside"),
            "is_internal": p.internal,
            "is_custodian": p.custodian,
        }
        for p in people
    ]
    return schemas.conform(pl.DataFrame(rows), "entities_p")


def communities(groups: dict[Person, int]) -> pl.DataFrame:
    rows = [{"pid": p.pid, "community": c} for p, c in groups.items()]
    return schemas.conform(pl.DataFrame(rows), "communities")


def people(*labels: str, custodian: bool = False) -> list[Person]:
    return [Person(label, custodian=custodian) for label in labels]
