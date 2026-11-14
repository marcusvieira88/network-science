"""Stage table contracts v1 (specs/001-enron-network-analysis/contracts/data-contracts.md).

These schemas are the interfaces between work packages. Change them only through the lead,
with a version bump and a note in docs/ai-workflow-log.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import polars as pl

from enron_case.contracts import vocab as v
from enron_case.errors import ContractViolation
from enron_case.zones import Zone

CONTRACT_VERSION = "1.1"

STR = pl.String()
INT = pl.Int64()
FLOAT = pl.Float64()
BOOL = pl.Boolean()
DATE = pl.Date()
TS = pl.Datetime("us", "UTC")
STR_LIST = pl.List(pl.String())
RECIPIENTS = pl.List(pl.Struct({"addr": pl.String(), "role": pl.String()}))

HEX16 = r"^[0-9a-f]{16}$"
HEX20 = r"^[0-9a-f]{20}$"
PID = v.PSEUDONYM_PATTERN
ORG = v.ORG_PSEUDONYM_PATTERN
EVENT_ID = r"^e_[a-z2-7]{16}$"
MSG_PID = r"^m_[a-z2-7]{16}$"


@dataclass(frozen=True)
class Col:
    name: str
    dtype: pl.DataType
    nullable: bool = False
    enum: tuple[str, ...] | None = None
    pattern: str | None = None


@dataclass(frozen=True)
class Table:
    name: str
    zone: Zone
    cols: tuple[Col, ...]
    sort: tuple[str, ...]
    fmt: str = "parquet"  # "parquet" or "csv"

    @property
    def filename(self) -> str:
        return f"{self.name}.{self.fmt}"

    @property
    def polars_schema(self) -> dict[str, pl.DataType]:
        return {c.name: c.dtype for c in self.cols}


def _t(name: str, zone: Zone, sort: tuple[str, ...], *cols: Col, fmt: str = "parquet") -> Table:
    return Table(name=name, zone=zone, cols=cols, sort=sort, fmt=fmt)


_HYPOTHESIS_COLS = (
    Col("hypothesis", STR, enum=v.HYPOTHESES),
    Col("metric", STR, enum=v.METRICS),
    Col("scope", STR, enum=v.SCOPES),
    Col("change_week", DATE, nullable=True),
    Col("p_perm", FLOAT),
    Col("p_holm", FLOAT),
    Col("effect", FLOAT),
    Col("ci_low", FLOAT),
    Col("ci_high", FLOAT),
    Col("null_z", FLOAT),
    Col("loo_min_effect", FLOAT),
    Col("loo_max_effect", FLOAT),
    Col("robust_variants_passed", INT),
    Col("robust_variants_total", INT),
    Col("supported", STR, enum=v.SUPPORT),
    Col("confidence", STR, enum=v.CONFIDENCE),
    Col("is_headline", BOOL),
)

_RISK_COLS = (
    Col("release_variant", STR, enum=v.RELEASE_VARIANTS),
    Col("attacker", STR, enum=v.ATTACKERS),
    Col("n_targets", INT),
    Col("unique_share", FLOAT),
    Col("median_anonymity_set", FLOAT),
    Col("reid_top1", FLOAT),
    Col("reid_ci_low", FLOAT),
    Col("reid_ci_high", FLOAT),
    Col("utility_effect_ratio", FLOAT, nullable=True),
    Col("finding_survives", BOOL, nullable=True),
)

TABLES: dict[str, Table] = {
    t.name: t
    for t in (
        # ---- Zone 1: ingest (identifiers present; purged at end of run) ----
        _t(
            "header_records",
            Zone.INGEST,
            ("file_id",),
            Col("file_id", STR, pattern=HEX16),
            Col("mailbox_owner", STR),
            Col("folder_class", STR, enum=v.FOLDER_CLASSES),
            Col("date_raw_ok", BOOL),
            Col("ts_utc", TS, nullable=True),
            Col("from_addr", STR, nullable=True),
            Col("to_addrs", STR_LIST),
            Col("cc_addrs", STR_LIST),
            Col("bcc_addrs", STR_LIST),
            Col("x_from", STR, nullable=True),
            Col("x_to", STR, nullable=True),
            Col("x_cc", STR, nullable=True),
            Col("x_bcc", STR, nullable=True),
            Col("message_id", STR, nullable=True),
            Col("parse_flags", STR_LIST),
        ),
        _t(
            "messages",
            Zone.INGEST,
            ("msg_key",),
            Col("msg_key", STR, pattern=HEX20),
            Col("ts_utc", TS, nullable=True),
            Col("sender_addr", STR, nullable=True),
            Col("recipients", RECIPIENTS),
            Col("n_recipients", INT),
            Col("n_copies", INT),
            Col("dedupe_rule", STR, enum=v.DEDUPE_RULES),
            Col("owner_copies", STR_LIST),
            Col("sent_copy_owner", STR, nullable=True),
            Col("flags", STR_LIST),
        ),
        _t(
            "entities",
            Zone.INGEST,
            ("entity_id",),
            Col("entity_id", STR),
            Col("type", STR, enum=v.ENTITY_TYPES),
            Col("org_domain", STR),
            Col("is_internal", BOOL),
            Col("is_custodian", BOOL),
            Col("n_addresses", INT),
        ),
        _t(
            "address_map",
            Zone.INGEST,
            ("addr",),
            Col("addr", STR),
            Col("entity_id", STR),
            Col("rule", STR, nullable=True, enum=v.IDENTITY_RULES),
            Col("support", INT),
        ),
        # ---- Zone 2: restricted (pseudonyms only) ----
        _t(
            "events",
            Zone.RESTRICTED,
            ("ts_hour", "sender_pid", "recipient_pid", "event_id"),
            Col("event_id", STR, pattern=EVENT_ID),
            Col("msg_pid", STR, pattern=MSG_PID),
            Col("ts_hour", TS),
            Col("sender_pid", STR, pattern=PID),
            Col("recipient_pid", STR, pattern=PID),
            Col("role", STR, enum=v.RECIPIENT_ROLES),
            Col("n_recipients", INT),
            Col("weight", FLOAT),
            Col("sender_type", STR, enum=v.ENTITY_TYPES),
            Col("recipient_type", STR, enum=v.ENTITY_TYPES),
            Col("sender_internal", BOOL),
            Col("recipient_internal", BOOL),
            Col("sender_org_pid", STR, pattern=ORG),
            Col("recipient_org_pid", STR, pattern=ORG),
            Col("in_network", BOOL),
        ),
        _t(
            "entities_p",
            Zone.RESTRICTED,
            ("pid",),
            Col("pid", STR, pattern=PID),
            Col("type", STR, enum=v.ENTITY_TYPES),
            Col("org_pid", STR, pattern=ORG),
            Col("is_internal", BOOL),
            Col("is_custodian", BOOL),
        ),
        _t(
            "snapshots",
            Zone.RESTRICTED,
            ("scope", "week", "src_pid", "dst_pid"),
            Col("scope", STR, enum=v.SCOPES),
            Col("week", DATE),
            Col("src_pid", STR, pattern=PID),
            Col("dst_pid", STR, pattern=PID),
            Col("weight", FLOAT),
            Col("n_messages", INT),
        ),
        _t(
            "metric_series",
            Zone.RESTRICTED,
            ("scope", "metric", "variant", "week"),
            Col("scope", STR, enum=v.SCOPES),
            Col("week", DATE),
            Col("metric", STR, enum=v.METRICS),
            Col("value", FLOAT, nullable=True),
            Col("n_active", INT),
            Col("variant", STR),
        ),
        _t(
            "communities",
            Zone.RESTRICTED,
            ("pid",),
            Col("pid", STR, pattern=PID),
            Col("community", INT),
        ),
        _t("hypothesis_results", Zone.RESTRICTED, ("hypothesis",), *_HYPOTHESIS_COLS),
        _t("risk_results", Zone.RESTRICTED, ("release_variant", "attacker"), *_RISK_COLS),
        # ---- Zone 3: release (aggregates, k-thresholded; committed) ----
        _t(
            "data_quality",
            Zone.RELEASE,
            ("order",),
            Col("order", INT),
            Col("step", STR),
            Col("count_in", INT),
            Col("count_out", INT),
            Col("removed", INT),
            Col("rule", STR, nullable=True),
            Col("precision", FLOAT, nullable=True),
            Col("recall", FLOAT, nullable=True),
            fmt="csv",
        ),
        _t(
            "header_fields",
            Zone.RELEASE,
            ("field",),
            Col("field", STR),
            Col("occurrences", INT),
            Col("ruling", STR),
            fmt="csv",
        ),
        _t(
            "weekly_metrics",
            Zone.RELEASE,
            ("scope", "metric", "variant", "week"),
            Col("scope", STR, enum=v.SCOPES),
            Col("week", DATE),
            Col("metric", STR, enum=v.METRICS),
            Col("value", FLOAT, nullable=True),
            Col("n_active", INT, nullable=True),
            Col("variant", STR),
            fmt="csv",
        ),
        _t("hypotheses", Zone.RELEASE, ("hypothesis",), *_HYPOTHESIS_COLS, fmt="csv"),
        _t("risk", Zone.RELEASE, ("release_variant", "attacker"), *_RISK_COLS, fmt="csv"),
        _t(
            "degree_distribution",
            Zone.RELEASE,
            ("period", "degree_bucket"),
            Col("period", STR),
            Col("degree_bucket", STR),
            Col("persons", INT, nullable=True),
            fmt="csv",
        ),
        _t(
            "community_graph",
            Zone.RELEASE,
            ("week", "src_group", "dst_group"),
            Col("week", DATE),
            Col("src_group", STR),
            Col("dst_group", STR),
            Col("weight", FLOAT, nullable=True),
            Col("n_messages", INT, nullable=True),
            fmt="csv",
        ),
        _t(
            "community_groups",
            Zone.RELEASE,
            ("group",),
            Col("group", STR),
            Col("n_persons", INT),
            fmt="csv",
        ),
    )
}


def table(name: str) -> Table:
    try:
        return TABLES[name]
    except KeyError as exc:
        raise ContractViolation(f"unknown table: {name}") from exc


def conform(df: pl.DataFrame, name: str) -> pl.DataFrame:
    """Select contract columns in order, cast to contract types and sort by the sort key."""
    spec = table(name)
    missing = [c.name for c in spec.cols if c.name not in df.columns]
    extra = [c for c in df.columns if c not in spec.polars_schema]
    if missing or extra:
        raise ContractViolation(f"{name}: missing columns {missing}, extra columns {extra}")
    out = df.select([pl.col(c.name).cast(c.dtype) for c in spec.cols])
    return out.sort(list(spec.sort), nulls_last=True, maintain_order=True)


def validate(df: pl.DataFrame, name: str) -> None:
    """Raise ContractViolation unless `df` matches the contract exactly (columns, types,
    nullability, enums, patterns, sort order)."""
    spec = table(name)
    names = [c.name for c in spec.cols]
    if df.columns != names:
        raise ContractViolation(f"{name}: columns {df.columns} != contract {names}")
    for col in spec.cols:
        series = df.get_column(col.name)
        if series.dtype != col.dtype:
            raise ContractViolation(f"{name}.{col.name}: dtype {series.dtype} != {col.dtype}")
        if not col.nullable and series.null_count() > 0:
            raise ContractViolation(f"{name}.{col.name}: nulls in non-nullable column")
        values = series.drop_nulls()
        if col.enum is not None:
            bad = values.filter(~values.is_in(list(col.enum)))
            if len(bad) > 0:
                raise ContractViolation(f"{name}.{col.name}: {len(bad)} values outside enum")
        if col.pattern is not None:
            bad_count = len(values) - int(values.str.contains(col.pattern).sum())
            if bad_count:
                raise ContractViolation(f"{name}.{col.name}: {bad_count} values break pattern")
    sorted_df = df.sort(list(spec.sort), nulls_last=True, maintain_order=True)
    if not df.equals(sorted_df):
        raise ContractViolation(f"{name}: not sorted by {spec.sort}")


def leak_count(df: pl.DataFrame, patterns: tuple[str, ...] = v.LEAK_PATTERNS) -> int:
    """Number of string cells (including list elements) matching any identifier pattern."""
    combined = "|".join(f"(?:{p})" for p in patterns)
    total = 0
    for name, dtype in df.schema.items():
        series = df.get_column(name)
        if dtype == STR:
            total += int(series.drop_nulls().str.contains(combined).sum())
        elif dtype == STR_LIST:
            exploded = series.explode().drop_nulls()
            total += int(exploded.str.contains(combined).sum())
    return total


def is_pattern(value: str, pattern: str) -> bool:
    return re.fullmatch(pattern.strip("^$"), value) is not None
