"""Keyed pseudonyms and the restricted-zone tables built from them (research R5).

Addresses and entity ids are hashed here and never leave this module: the returned tables
hold pseudonyms only, and no address-to-pseudonym mapping is kept or written.
"""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl

from enron_case.contracts import schemas
from enron_case.contracts import vocab as v
from enron_case.contracts.vocab import ROLE_STRENGTH
from enron_case.errors import ContractViolation, PseudonymCollision
from enron_case.pseudo.keys import EVENT_LABEL, ORG_LABEL, PERSON_LABEL, keyed_digest

# Message flags that take a message out of the network (data-contracts.md, events.in_network).
EXCLUSION_FLAGS = ("date_out_of_range", "no_recipients", "self_only", "mass_mailing")
EVENT_ID_SEPARATOR = "|"


def person_pid(key: bytes, entity_id: str) -> str:
    return v.format_pseudonym(v.PERSON_PREFIX, keyed_digest(key, PERSON_LABEL, entity_id))


def org_pid(key: bytes, org_domain: str) -> str:
    return v.format_pseudonym(v.ORG_PREFIX, keyed_digest(key, ORG_LABEL, org_domain))


def message_pid(key: bytes, msg_key: str) -> str:
    return v.format_pseudonym(v.MESSAGE_PREFIX, keyed_digest(key, EVENT_LABEL, msg_key))


def event_id(key: bytes, msg_key: str, recipient_addr: str) -> str:
    value = msg_key + EVENT_ID_SEPARATOR + recipient_addr
    return v.format_pseudonym(v.EVENT_PREFIX, keyed_digest(key, EVENT_LABEL, value))


def assert_unique(inputs: Sequence[str], pids: Sequence[str], kind: str) -> None:
    """Abort if distinct inputs share a pseudonym. The message carries counts only."""
    distinct_inputs = len(set(inputs))
    distinct_pids = len(set(pids))
    if distinct_pids != distinct_inputs:
        raise PseudonymCollision(
            f"{distinct_inputs} distinct {kind} ids gave {distinct_pids} distinct pseudonyms"
        )


def _pid_lookup(key: bytes, entities: pl.DataFrame) -> pl.DataFrame:
    """entity_id -> pid, org_pid, with the collision check on both."""
    entity_ids = entities["entity_id"].to_list()
    domains = entities["org_domain"].to_list()
    pids = [person_pid(key, e) for e in entity_ids]
    assert_unique(entity_ids, pids, "entity")
    org_by_domain = {d: org_pid(key, d) for d in sorted(set(domains))}
    assert_unique(list(org_by_domain), list(org_by_domain.values()), "organization")
    return entities.with_columns(
        pl.Series("pid", pids, dtype=pl.String),
        pl.Series("org_pid", [org_by_domain[d] for d in domains], dtype=pl.String),
    )


def build_entities_p(key: bytes, entities: pl.DataFrame) -> pl.DataFrame:
    lookup = _pid_lookup(key, entities)
    return schemas.conform(
        lookup.select("pid", "type", "org_pid", "is_internal", "is_custodian"), "entities_p"
    )


def build_events(
    key: bytes, messages: pl.DataFrame, entities: pl.DataFrame, address_map: pl.DataFrame
) -> pl.DataFrame:
    """One row per (message, recipient entity) for messages with a timestamp and a sender.

    Several addresses of one recipient entity collapse into one event with the strongest role;
    a recipient that is the sender's own entity (an alias) is dropped; `n_recipients` and
    `weight` count recipient entities, not addresses."""
    pairs = _message_recipient_pairs(messages)
    pid_table = _pid_lookup(key, entities).select(
        "entity_id", "pid", "type", "is_internal", "org_pid"
    )
    addr_to_entity = address_map.select("addr", "entity_id")
    repeated = addr_to_entity.height - addr_to_entity["addr"].n_unique()
    if repeated:
        raise ContractViolation(f"address_map lists {repeated} addresses more than once")
    resolved = _attach(pairs, addr_to_entity, pid_table, "sender_addr", "sender")
    resolved = _per_recipient_entity(
        _attach(resolved, addr_to_entity, pid_table, "addr", "recipient")
    )
    keyed = resolved.with_columns(
        pl.Series(
            "event_id",
            [
                event_id(key, m, a)
                for m, a in zip(resolved["msg_key"], resolved["addr"], strict=True)
            ],
            dtype=pl.String,
        ),
        pl.Series("msg_pid", [message_pid(key, m) for m in resolved["msg_key"]], dtype=pl.String),
    )
    return schemas.conform(keyed.drop("msg_key", "sender_addr", "addr"), "events")


def _per_recipient_entity(resolved: pl.DataFrame) -> pl.DataFrame:
    rank = pl.col("role").replace_strict(ROLE_STRENGTH, return_dtype=pl.Int64)
    collapsed = (
        resolved.filter(pl.col("sender_pid") != pl.col("recipient_pid"))
        .with_columns(rank.alias("_rank"))
        .sort(["msg_key", "recipient_pid", "_rank", "addr"], descending=[False, False, True, False])
        .unique(subset=["msg_key", "recipient_pid"], keep="first", maintain_order=True)
        .drop("_rank")
    )
    return collapsed.with_columns(
        pl.len().over("msg_key").cast(pl.Int64).alias("n_recipients")
    ).with_columns((1.0 / pl.col("n_recipients")).alias("weight"))


def _message_recipient_pairs(messages: pl.DataFrame) -> pl.DataFrame:
    return (
        messages.filter(pl.col("ts_utc").is_not_null() & pl.col("sender_addr").is_not_null())
        .filter(pl.col("recipients").list.len() > 0)
        .select(
            "msg_key",
            "sender_addr",
            "recipients",
            "n_recipients",
            pl.col("ts_utc").dt.truncate("1h").alias("ts_hour"),
            (1.0 / pl.col("n_recipients")).alias("weight"),
            ~pl.col("flags")
            .list.eval(pl.element().is_in(list(EXCLUSION_FLAGS)))
            .list.any()
            .alias("in_network"),
        )
        .explode("recipients")
        .unnest("recipients")
    )


def _attach(
    pairs: pl.DataFrame,
    addr_to_entity: pl.DataFrame,
    pid_table: pl.DataFrame,
    addr_column: str,
    side: str,
) -> pl.DataFrame:
    """Add `<side>_pid`, `<side>_type`, `<side>_internal`, `<side>_org_pid` via the entity."""
    joined = pairs.join(
        addr_to_entity.rename({"addr": addr_column}), on=addr_column, how="left"
    ).join(pid_table, on="entity_id", how="left")
    unresolved = joined["pid"].null_count()
    if unresolved:
        raise ContractViolation(f"{unresolved} {side} addresses have no entity in address_map")
    return joined.drop("entity_id").rename(
        {
            "pid": f"{side}_pid",
            "type": f"{side}_type",
            "is_internal": f"{side}_internal",
            "org_pid": f"{side}_org_pid",
        }
    )
