"""Contract fixtures derived from synthetic ground truth.

Each table here is the *reference answer* for its stage on the synthetic archive, built from
what the generator knows, not by running pipeline code. Agents test their stage against these.
Values for analytical tables (metric_series onward) are synthetic series with known structure,
not computed from snapshots, so no stage logic is duplicated here.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import random
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import polars as pl

from enron_case.config import Config
from enron_case.contracts import schemas
from enron_case.contracts import vocab as v
from enron_case.release import tables as release_tables
from enron_case.synth.archive import FileRecord
from enron_case.synth.model import Entity, Message, Organisation, SynthSpec

# Fixture-only key. Never used for real data.
FIXTURE_KEY = b"fixture-key-for-synthetic-data-only"
# Reference rulings (contracts/header-allowlist.md); the parser emits its own in ingest_counts.
HEADER_RULINGS = {
    "Date": "usable",
    "From": "identifier",
    "To": "identifier",
    "Cc": "identifier",
    "Bcc": "identifier",
    "X-From": "identifier",
    "X-To": "identifier",
    "X-cc": "identifier",
    "X-bcc": "identifier",
    "X-Origin": "identifier",
    "X-Folder": "content",
    "Subject": "content",
    "Message-ID": "technical",
    "X-FileName": "identifier",
    "Mime-Version": "dropped",
    "Content-Type": "dropped",
    "Content-Transfer-Encoding": "dropped",
}
EXCLUSION_FLAGS = {"date_out_of_range", "no_recipients", "self_only", "mass_mailing"}


def _digest(label: str, value: str) -> bytes:
    subkey = hmac.new(FIXTURE_KEY, label.encode(), hashlib.sha256).digest()
    return hmac.new(subkey, value.encode(), hashlib.sha256).digest()


def fixture_pid(entity_id: str) -> str:
    return v.format_pseudonym(v.PERSON_PREFIX, _digest("person-v1", entity_id))


def fixture_org_pid(domain: str) -> str:
    return v.format_pseudonym(v.ORG_PREFIX, _digest("org-v1", domain))


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _valid(addr: str) -> bool:
    return "@" in addr and not addr.endswith(":;")


class FixtureBuilder:
    """Builds every contract table for one synthetic corpus."""

    def __init__(
        self, spec: SynthSpec, org: Organisation, messages: list[Message], files: list[FileRecord]
    ) -> None:
        self.spec = spec
        self.org = org
        self.files = files
        self.config = Config(internal_domain=spec.domain)
        self.by_addr = {a.lower(): e for e in org.everyone for a in e.addresses}
        self.copies: dict[str, list[FileRecord]] = defaultdict(list)
        for record in files:
            self.copies[record.message.truth_id].append(record)
        self.messages = [m for m in messages if m.truth_id in self.copies]
        self._entity_ids: dict[str, str] = {}

    # ---- ingest zone ----------------------------------------------------------------------
    def header_records(self) -> pl.DataFrame:
        rows = []
        for f in self.files:
            msg = f.message
            flags = []
            if msg.ts_utc is None:
                flags.append("bad_date")
            if f.folded:
                flags.append("folded")
            rows.append(
                {
                    "file_id": v.file_id(f.member_path),
                    "mailbox_owner": f.owner.owner_dir,
                    "folder_class": v.folder_class(f.folder),
                    "date_raw_ok": msg.ts_utc is not None,
                    "ts_utc": msg.ts_utc,
                    "from_addr": msg.sender_addr,
                    "to_addrs": f.to,
                    "cc_addrs": f.cc,
                    "bcc_addrs": f.bcc,
                    "x_from": msg.sender.display_name,
                    "x_to": f.x_to,
                    "x_cc": f.x_cc,
                    "x_bcc": f.x_bcc,
                    "message_id": f.message_id,
                    "parse_flags": sorted(flags),
                }
            )
        return schemas.conform(
            pl.DataFrame(rows, schema=schemas.table("header_records").polars_schema),
            "header_records",
        )

    def _recipients(self, msg: Message) -> list[dict[str, str]]:
        sender_custodian = msg.sender.is_custodian
        roles: dict[str, str] = {}
        fields = [("to", msg.to), ("cc", msg.cc)]
        if sender_custodian:
            fields.append(("bcc", msg.bcc))
        for role, addrs in fields:
            for raw in addrs:
                addr = raw.lower()
                if not _valid(addr):
                    continue
                if addr not in roles or v.ROLE_STRENGTH[role] > v.ROLE_STRENGTH[roles[addr]]:
                    roles[addr] = role
        return [{"addr": a, "role": roles[a]} for a in sorted(roles)]

    def message_rows(self) -> list[dict[str, Any]]:
        rows = []
        for msg in self.messages:
            copies = self.copies[msg.truth_id]
            recipients = self._recipients(msg)
            sender = msg.sender_addr.lower()
            addrs = [r["addr"] for r in recipients]
            flags = set(msg.noise) & set(v.MESSAGE_FLAGS)
            if not recipients:
                flags.add("no_recipients")
            if addrs == [sender]:
                flags.add("self_only")
            if len(recipients) > self.config.recipient_cap:
                flags.add("mass_mailing")
            if any(not _valid(a.lower()) for a in [*msg.to, *msg.cc]):
                flags.add("bad_address")
            sets = {tuple(sorted({*c.to, *c.cc, *c.bcc})) for c in copies}
            rule = "none" if len(copies) == 1 else ("subset" if len(sets) > 1 else "exact")
            rows.append(
                {
                    "msg_key": v.msg_key(sender, msg.ts_utc, addrs),
                    "ts_utc": msg.ts_utc,
                    "sender_addr": sender,
                    "recipients": recipients,
                    "n_recipients": len(recipients),
                    "n_copies": len(copies),
                    "dedupe_rule": rule,
                    "owner_copies": sorted({c.owner.owner_dir or "" for c in copies}),
                    "sent_copy_owner": msg.sender.owner_dir if msg.sender.is_custodian else None,
                    "flags": sorted(flags),
                    "_truth": msg.truth_id,
                }
            )
        return rows

    def messages_table(self) -> pl.DataFrame:
        rows = [{k: val for k, val in r.items() if k != "_truth"} for r in self.message_rows()]
        df = pl.DataFrame(rows, schema=schemas.table("messages").polars_schema)
        return schemas.conform(df, "messages")

    def _observed(self) -> dict[str, int]:
        support: dict[str, int] = defaultdict(int)
        for row in self.message_rows():
            support[row["sender_addr"]] += 1
            for r in row["recipients"]:
                support[r["addr"]] += 1
        return dict(support)

    def entity_of(self, addr: str) -> Entity:
        return self.by_addr[addr]

    def entity_ids(self) -> dict[str, str]:
        """truth_id -> contract entity_id (smallest observed normalised address)."""
        if not self._entity_ids:
            observed: dict[str, list[str]] = defaultdict(list)
            for addr in self._observed():
                if addr in self.by_addr:
                    observed[self.by_addr[addr].truth_id].append(addr)
            self._entity_ids = {tid: min(addrs) for tid, addrs in observed.items()}
        return self._entity_ids

    def entities_table(self) -> pl.DataFrame:
        support = self._observed()
        ids = self.entity_ids()
        counts: dict[str, int] = defaultdict(int)
        for addr in support:
            if addr in self.by_addr:
                counts[self.by_addr[addr].truth_id] += 1
        rows = []
        for e in self.org.everyone:
            if e.truth_id not in ids:
                continue
            rows.append(
                {
                    "entity_id": ids[e.truth_id],
                    "type": e.type,
                    "org_domain": e.org_domain,
                    "is_internal": e.is_internal,
                    "is_custodian": e.is_custodian,
                    "n_addresses": counts[e.truth_id],
                }
            )
        df = pl.DataFrame(rows, schema=schemas.table("entities").polars_schema)
        return schemas.conform(df, "entities")

    def address_map_table(self) -> pl.DataFrame:
        ids = self.entity_ids()
        rows = []
        for addr, n in sorted(self._observed().items()):
            if addr not in self.by_addr:
                continue
            e = self.by_addr[addr]
            canonical = ids[e.truth_id]
            rule: str | None = None
            if addr != canonical:
                rule = "N2" if addr == e.subdomain_alias else "N3"
            rows.append({"addr": addr, "entity_id": canonical, "rule": rule, "support": n})
        df = pl.DataFrame(rows, schema=schemas.table("address_map").polars_schema)
        return schemas.conform(df, "address_map")

    # ---- restricted zone ------------------------------------------------------------------
    def events_table(self) -> pl.DataFrame:
        ids = self.entity_ids()
        rows = []
        for row in self.message_rows():
            if row["ts_utc"] is None or not row["recipients"]:
                continue
            sender = self.by_addr[row["sender_addr"]]
            # One event per recipient entity: strongest role, smallest address on ties; the
            # sender's own entity (an alias) is not a recipient.
            best: dict[str, dict[str, str]] = {}
            for r in sorted(
                row["recipients"], key=lambda r: (-v.ROLE_STRENGTH[r["role"]], r["addr"])
            ):
                tid = self.by_addr[r["addr"]].truth_id
                if tid != sender.truth_id and tid not in best:
                    best[tid] = r
            recipients = sorted(best.values(), key=lambda r: r["addr"])
            n = len(recipients)
            if n == 0:
                continue
            in_network = not (set(row["flags"]) & EXCLUSION_FLAGS)
            ts_hour = row["ts_utc"].replace(minute=0, second=0, microsecond=0)
            for r in recipients:
                recipient = self.by_addr[r["addr"]]
                rows.append(
                    {
                        "event_id": v.format_pseudonym(
                            v.EVENT_PREFIX, _digest("event-v1", row["msg_key"] + "|" + r["addr"])
                        ),
                        "msg_pid": v.format_pseudonym(
                            v.MESSAGE_PREFIX, _digest("event-v1", row["msg_key"])
                        ),
                        "ts_hour": ts_hour,
                        "sender_pid": fixture_pid(ids[sender.truth_id]),
                        "recipient_pid": fixture_pid(ids[recipient.truth_id]),
                        "role": r["role"],
                        "n_recipients": n,
                        "weight": 1.0 / n,
                        "sender_type": sender.type,
                        "recipient_type": recipient.type,
                        "sender_internal": sender.is_internal,
                        "recipient_internal": recipient.is_internal,
                        "sender_org_pid": fixture_org_pid(sender.org_domain),
                        "recipient_org_pid": fixture_org_pid(recipient.org_domain),
                        "in_network": in_network,
                    }
                )
        df = pl.DataFrame(rows, schema=schemas.table("events").polars_schema)
        return schemas.conform(df, "events")

    def entities_p_table(self) -> pl.DataFrame:
        ent = self.entities_table()
        df = ent.select(
            pl.col("entity_id").map_elements(fixture_pid, return_dtype=pl.Utf8).alias("pid"),
            "type",
            pl.col("org_domain")
            .map_elements(fixture_org_pid, return_dtype=pl.Utf8)
            .alias("org_pid"),
            "is_internal",
            "is_custodian",
        )
        return schemas.conform(df, "entities_p")

    def snapshots_table(self) -> pl.DataFrame:
        ev = self.events_table().filter(
            pl.col("in_network")
            & (pl.col("sender_type") == "person")
            & (pl.col("recipient_type") == "person")
            & pl.col("sender_internal")
            & pl.col("recipient_internal")
        )
        custodians = set(
            self.entities_p_table().filter(pl.col("is_custodian")).get_column("pid").to_list()
        )
        ev = ev.with_columns(
            pl.col("ts_hour").dt.date().dt.truncate("1w").alias("week"),
            (
                pl.col("sender_pid").is_in(custodians) & pl.col("recipient_pid").is_in(custodians)
            ).alias("core"),
        )
        frames = []
        for scope, frame in (("observed", ev), ("core", ev.filter(pl.col("core")))):
            agg = frame.group_by("week", "sender_pid", "recipient_pid").agg(
                pl.col("weight").sum(),
                pl.col("msg_pid").n_unique().cast(pl.Int64).alias("n_messages"),
            )
            frames.append(
                agg.select(
                    pl.lit(scope).alias("scope"),
                    "week",
                    pl.col("sender_pid").alias("src_pid"),
                    pl.col("recipient_pid").alias("dst_pid"),
                    "weight",
                    "n_messages",
                )
            )
        return schemas.conform(pl.concat(frames), "snapshots")

    def communities_table(self) -> pl.DataFrame:
        ids = self.entity_ids()
        rows = [
            {"pid": fixture_pid(ids[p.truth_id]), "community": p.community}
            for p in self.org.persons
            if p.truth_id in ids
        ]
        return schemas.conform(pl.DataFrame(rows), "communities")

    def weeks(self) -> list[date]:
        start, end = monday(self.config.analysis_start), self.config.analysis_end
        out, week = [], start
        while week <= end:
            out.append(week)
            week += timedelta(days=7)
        return out

    def metric_series_table(self) -> pl.DataFrame:
        """Synthetic series: flat with noise, plus a step at the change week for the H1 and
        H2 metrics when the change is planted."""
        rng = random.Random(self.spec.seed + 2)
        base = {
            "volume": 120.0,
            "active_persons": 40.0,
            "density": 0.08,
            "reciprocity": 0.35,
            "indegree_gini": 0.30,
            "cross_community_share": 0.15,
            "external_share": 0.12,
            "tie_turnover": 0.60,
        }
        step = {"indegree_gini": 0.15, "cross_community_share": 0.25}
        rows = []
        for scope, n_active in (("observed", 40), ("core", 12)):
            for metric in v.METRICS:
                for variant in ("default", "cap=20"):
                    for week in self.weeks():
                        jump = (
                            step.get(metric, 0.0)
                            if (self.spec.planted_change and week >= self.spec.change_week)
                            else 0.0
                        )
                        noise = rng.gauss(0.0, 0.04 * base[metric])
                        rows.append(
                            {
                                "scope": scope,
                                "week": week,
                                "metric": metric,
                                "value": base[metric] + jump + noise,
                                "n_active": n_active,
                                "variant": variant,
                            }
                        )
        return schemas.conform(pl.DataFrame(rows), "metric_series")

    def hypothesis_results_table(self) -> pl.DataFrame:
        cw = self.spec.change_week if self.spec.planted_change else None
        planted = self.spec.planted_change
        rows = [
            (
                "H1",
                "indegree_gini",
                "core",
                cw,
                0.002,
                0.008,
                1.8,
                1.2,
                2.4,
                4.1,
                1.5,
                2.0,
                3,
                3,
                "yes" if planted else "no",
                "high" if planted else "low",
                planted,
            ),
            (
                "H2",
                "cross_community_share",
                "observed",
                cw,
                0.004,
                0.012,
                1.5,
                0.9,
                2.1,
                3.2,
                1.1,
                1.7,
                2,
                3,
                "yes" if planted else "no",
                "moderate" if planted else "low",
                False,
            ),
            (
                "H3",
                "external_share",
                "observed",
                None,
                0.41,
                0.82,
                0.1,
                -0.3,
                0.5,
                0.4,
                -0.1,
                0.3,
                0,
                3,
                "no",
                "low",
                False,
            ),
            (
                "H4",
                "tie_turnover",
                "core",
                None,
                0.09,
                0.27,
                0.4,
                -0.1,
                0.9,
                1.1,
                0.0,
                0.7,
                1,
                3,
                "inconclusive",
                "low",
                False,
            ),
        ]
        cols = [c.name for c in schemas.table("hypothesis_results").cols]
        df = pl.DataFrame(
            [dict(zip(cols, r, strict=True)) for r in rows],
            schema=schemas.table("hypothesis_results").polars_schema,
        )
        return schemas.conform(df, "hypothesis_results")

    def risk_results_table(self) -> pl.DataFrame:
        rows = [
            ("R0", "A1", 50, 0.94, 1.0, 0.90, 0.82, 0.96, 1.0, True),
            ("R0", "A2", 50, 0.94, 1.0, 0.62, 0.48, 0.75, 1.0, True),
            ("R1", "A1", 50, 0.0, 12.0, 0.0, 0.0, 0.06, 0.97, True),
            ("R1", "A2", 50, 0.0, 12.0, 0.02, 0.0, 0.08, 0.97, True),
            ("R2", "A1", 50, 0.0, 12.0, 0.0, 0.0, 0.06, 0.91, True),
            ("R2", "A2", 50, 0.0, 12.0, 0.0, 0.0, 0.06, 0.91, True),
        ]
        cols = [c.name for c in schemas.table("risk_results").cols]
        df = pl.DataFrame(
            [dict(zip(cols, r, strict=True)) for r in rows],
            schema=schemas.table("risk_results").polars_schema,
        )
        return schemas.conform(df, "risk_results")

    def exploratory_results_table(self) -> pl.DataFrame:
        """Reference shape only: twenty rows, E12 confident with its volume-equalised check,
        E16 inconclusive, the caveated three marked, the rest not supported."""
        caveats = schemas.EXPLORATORY_CAVEATS
        rows = []
        for i in range(1, 21):
            hid = f"H{i + 4}"
            outcome = {"H16": "inconclusive", "H20": "inconclusive"}.get(hid, "not supported")
            strong = outcome != "not supported"
            rows.append(
                {
                    "order": i + 4,
                    "hypothesis": hid,
                    "family": schemas.EXPLORATORY_FAMILIES[0 if i < 11 else 1],
                    "measure": f"measure {hid}",
                    "direction": "down" if i in (7, 15, 18, 20) else "up",
                    "custodians": 32,
                    "median_change": 0.25 if strong else 0.01,
                    "ci_low": 0.12 if strong else -0.02,
                    "ci_high": 0.38 if strong else 0.04,
                    "p": 0.0001 if strong else 0.6,
                    "p_holm": 0.002 if strong else 1.0,
                    "placebo_custodians": 15,
                    "placebo_median": 0.0,
                    "placebo_ci_low": -0.03,
                    "placebo_ci_high": 0.04,
                    "placebo_passes": hid != "H20",
                    "loo_stable": strong,
                    "outcome": outcome,
                    "caveat": schemas.RETENTION_FAILED if hid == "H16" else caveats.get(hid, ""),
                    "equalised_median": 0.1 if strong else None,
                    "equalised_ci_low": 0.06 if strong else None,
                    "equalised_ci_high": 0.17 if strong else None,
                    "equalised_p": 0.001 if strong else None,
                    "equalised_p_holm": 0.02 if strong else None,
                    "retention_median": 0.11 if hid == "H16" else None,
                    "retention_ci_low": -0.1 if hid == "H16" else None,
                    "retention_ci_high": 0.3 if hid == "H16" else None,
                    "retention_passes": False if hid == "H16" else None,
                }
            )
        spec = schemas.table("exploratory_results")
        return schemas.conform(pl.DataFrame(rows, schema=spec.polars_schema), spec.name)

    def artifact_results_table(self) -> pl.DataFrame:
        """Planted change is behavioural and communities never drift: both checks pass."""
        rows = [
            {
                "hypothesis": "H2",
                "check": "baseline_placebo",
                "statistic": 0.4,
                "ci_low": -0.3,
                "ci_high": 1.1,
                "n_units": 26,
                "passes": True,
                "note": "out-of-sample jump within the calm baseline year is small",
            },
            {
                "hypothesis": "H3",
                "check": "within_custodian",
                "statistic": -0.05,
                "ci_low": -0.08,
                "ci_high": -0.02,
                "n_units": 12,
                "passes": True,
                "note": "custodians themselves shifted their mail inward",
            },
        ]
        return schemas.conform(
            pl.DataFrame(rows, schema=schemas.table("artifact_results").polars_schema),
            "artifact_results",
        )

    # ---- counts side outputs ----------------------------------------------------------------
    def counts(self) -> dict[str, dict[str, Any]]:
        header = self.header_records()
        msgs = self.message_rows()
        flags: dict[str, int] = defaultdict(int)
        for row in msgs:
            for flag in row["flags"]:
                flags[flag] += 1
        ids = self.entity_ids()
        amap = self.address_map_table()
        events = self.events_table()
        n_files = header.height
        fields = [
            "Message-ID",
            "Date",
            "From",
            "To",
            "Cc",
            "Bcc",
            "Subject",
            "Mime-Version",
            "Content-Type",
            "Content-Transfer-Encoding",
            "X-From",
            "X-To",
            "X-cc",
            "X-bcc",
            "X-Folder",
            "X-Origin",
            "X-FileName",
        ]
        return {
            "ingest_counts": {
                "files_seen": n_files,
                "files_parsed": n_files,
                "rejected": {},
                "header_fields": dict.fromkeys(fields, n_files),
                "header_rulings": HEADER_RULINGS,
                "parse_flags": {
                    "bad_date": int(
                        header.get_column("parse_flags").list.contains("bad_date").sum()
                    ),
                    "folded": int(header.get_column("parse_flags").list.contains("folded").sum()),
                },
            },
            "clean_counts": {
                "records_in": n_files,
                "messages_out": len(msgs),
                "removed_exact": sum(
                    r["n_copies"] - 1 for r in msgs if r["dedupe_rule"] == "exact"
                ),
                "removed_subset": sum(
                    r["n_copies"] - 1 for r in msgs if r["dedupe_rule"] == "subset"
                ),
                "flags": dict(flags),
                "message_id_shared_share": 0.0,
                "dedupe_precision": 1.0,
                "dedupe_recall": 1.0,
            },
            "identity_counts": {
                "addresses": amap.height,
                "entities": len(ids),
                "entities_by_type": {
                    t: int(c) for t, c in self.entities_table().group_by("type").len().iter_rows()
                },
                "merges_by_rule": {
                    r: int(c) for r, c in amap.drop_nulls("rule").group_by("rule").len().iter_rows()
                },
                "blocked_by_guard": {"cross_org": 1},
                "cluster_sizes": {},
                "precision": 1.0,
                "recall": 1.0,
                "manual_checked": None,
                "manual_correct": None,
            },
            "pseudo_counts": {
                "entities": len(ids),
                "events": events.height,
                "messages_without_time": sum(1 for r in msgs if r["ts_utc"] is None),
                "events_in_network": int(events.get_column("in_network").sum()),
            },
        }

    # ---- release zone ---------------------------------------------------------------------
    def release_tables(self) -> dict[str, pl.DataFrame]:
        k = self.config.k_min
        c = self.counts()
        dq = pl.DataFrame(
            [
                {
                    "order": 1,
                    "step": "files parsed",
                    "count_in": c["ingest_counts"]["files_seen"],
                    "count_out": c["ingest_counts"]["files_parsed"],
                    "removed": 0,
                    "rule": None,
                    "precision": None,
                    "recall": None,
                    "precision_ci_low": None,
                    "precision_ci_high": None,
                },
                {
                    "order": 2,
                    "step": "deduplicate",
                    "count_in": c["clean_counts"]["records_in"],
                    "count_out": c["clean_counts"]["messages_out"],
                    "removed": c["clean_counts"]["records_in"] - c["clean_counts"]["messages_out"],
                    "rule": "exact+subset",
                    "precision": 1.0,
                    "recall": 1.0,
                    "precision_ci_low": None,
                    "precision_ci_high": None,
                },
                {
                    "order": 3,
                    "step": "resolve identities",
                    "count_in": c["identity_counts"]["addresses"],
                    "count_out": c["identity_counts"]["entities"],
                    "removed": c["identity_counts"]["addresses"] - c["identity_counts"]["entities"],
                    "rule": "N1-N4",
                    "precision": 1.0,
                    "recall": 1.0,
                    "precision_ci_low": None,
                    "precision_ci_high": None,
                },
                *self._funnel_detail_rows(c, first_order=4),
            ]
        )
        rulings = HEADER_RULINGS
        hf = pl.DataFrame(
            [
                {"field": f, "occurrences": n, "ruling": rulings[f]}
                for f, n in c["ingest_counts"]["header_fields"].items()
            ]
        )
        default = self.metric_series_table().filter(pl.col("variant") == "default")
        weekly = default.with_columns(
            pl.when(pl.col("n_active") >= k).then(pl.col("value")).alias("value"),
            pl.when(pl.col("n_active") >= k).then(pl.col("n_active")).alias("n_active"),
        )
        # The 3 in `10+` is each period's only hidden non-zero cell, so the smallest published
        # cell (the 6 in `1`) is suppressed with it (complementary suppression).
        degree = pl.DataFrame(
            [
                {"period": p, "degree_bucket": b, "persons": n}
                for p in ("2000H1", "2000H2", "2001H1", "2001H2")
                for b, n in (("1", None), ("2-4", 18), ("5-9", 14), ("10+", None))
            ],
            schema={"period": pl.Utf8, "degree_bucket": pl.Utf8, "persons": pl.Int64},
        )
        comm = self.communities_table()
        labels = {i: f"G{i + 1:02d}" for i in sorted(set(comm.get_column("community").to_list()))}
        snap = self.snapshots_table().filter(pl.col("scope") == "observed")
        joined = snap.join(
            comm.rename({"pid": "src_pid", "community": "src_c"}), on="src_pid"
        ).join(comm.rename({"pid": "dst_pid", "community": "dst_c"}), on="dst_pid")
        graph = (
            joined.group_by("week", "src_c", "dst_c")
            .agg(
                pl.col("weight").sum(),
                pl.col("n_messages").sum(),
                pl.col("src_pid").n_unique().alias("senders"),
            )
            .filter(pl.col("senders") >= k)
            .select(
                "week",
                pl.col("src_c").replace_strict(labels, return_dtype=pl.Utf8).alias("src_group"),
                pl.col("dst_c").replace_strict(labels, return_dtype=pl.Utf8).alias("dst_group"),
                "weight",
                "n_messages",
            )
        )
        groups = (
            comm.group_by("community")
            .len()
            .select(
                pl.col("community").replace_strict(labels, return_dtype=pl.Utf8).alias("group"),
                pl.col("len").cast(pl.Int64).alias("n_persons"),
            )
        )
        out = {
            "data_quality": dq,
            "header_fields": hf,
            "weekly_metrics": weekly,
            "hypotheses": self.hypothesis_results_table(),
            "risk": self.risk_results_table(),
            "artifact_checks": self.artifact_results_table(),
            "exploratory": self.exploratory_results_table(),
            "degree_distribution": degree,
            "community_graph": graph,
            "community_groups": groups,
        }
        return {name: schemas.conform(df, name) for name, df in out.items()}

    def _funnel_detail_rows(
        self, c: dict[str, dict[str, Any]], first_order: int
    ) -> list[dict[str, Any]]:
        """Reference funnel detail, counted from the fixture's own messages and events: no
        rejected files, the exact/subset split, the five flags and events in the network."""
        msgs = self.message_rows()
        events = self.events_table()
        records = len(self.header_records())
        exact = sum(r["n_copies"] - 1 for r in msgs if r["dedupe_rule"] == "exact")
        flagged = {flag: sum(1 for r in msgs if flag in r["flags"]) for flag in v.MESSAGE_FLAGS}
        steps = [
            (release_tables.STEP_EXACT, records, records - exact, release_tables.RULE_EXACT),
            (release_tables.STEP_SUBSET, records - exact, len(msgs), release_tables.RULE_SUBSET),
            *[
                (
                    release_tables.STEP_FLAG.format(flag=name),
                    len(msgs),
                    len(msgs) - flagged[flag],
                    release_tables.RULE_FLAG_KEPT
                    if flag == "bad_address"
                    else release_tables.RULE_FLAG_EXCLUDED,
                )
                for flag, name in release_tables.FLAG_NAMES.items()
            ],
            (
                release_tables.STEP_UNTIMED,
                len(msgs),
                len(msgs) - sum(1 for r in msgs if r["ts_utc"] is None),
                release_tables.RULE_UNTIMED,
            ),
            (
                release_tables.STEP_EVENTS,
                events.height,
                int(events.get_column("in_network").sum()),
                release_tables.RULE_EVENTS,
            ),
        ]
        return [
            {
                "order": first_order + i,
                "step": step,
                "count_in": count_in,
                "count_out": count_out,
                "removed": count_in - count_out,
                "rule": rule,
                "precision": None,
                "recall": None,
                "precision_ci_low": None,
                "precision_ci_high": None,
            }
            for i, (step, count_in, count_out, rule) in enumerate(steps)
        ]

    def all_tables(self) -> dict[str, pl.DataFrame]:
        tables = {
            "header_records": self.header_records(),
            "messages": self.messages_table(),
            "entities": self.entities_table(),
            "address_map": self.address_map_table(),
            "events": self.events_table(),
            "entities_p": self.entities_p_table(),
            "snapshots": self.snapshots_table(),
            "communities": self.communities_table(),
            "metric_series": self.metric_series_table(),
            "hypothesis_results": self.hypothesis_results_table(),
            "risk_results": self.risk_results_table(),
            "artifact_results": self.artifact_results_table(),
            "exploratory_results": self.exploratory_results_table(),
        }
        tables.update(self.release_tables())
        return tables

    # ---- ground truth ---------------------------------------------------------------------
    def truth(self) -> dict[str, Any]:
        ids = self.entity_ids()
        entities = []
        for e in self.org.everyone:
            entities.append(
                {
                    "truth_id": e.truth_id,
                    "entity_id": ids.get(e.truth_id),
                    "type": e.type,
                    "addresses": e.addresses,
                    "display_name": e.display_name,
                    "org_domain": e.org_domain,
                    "is_internal": e.is_internal,
                    "is_custodian": e.is_custodian,
                    "owner_dir": e.owner_dir,
                    "community": e.community,
                }
            )
        return {
            "spec": {
                "seed": self.spec.seed,
                "planted_change": self.spec.planted_change,
                "change_week": self.spec.change_week.isoformat(),
                "domain": self.spec.domain,
            },
            "entities": entities,
            "address_to_truth": {
                a.lower(): e.truth_id for e in self.org.everyone for a in e.addresses
            },
            "file_to_message": {f.member_path: f.message.truth_id for f in self.files},
            "hubs": [h.truth_id for h in self.org.hubs],
            "canary_markers": ["CANARYBODY", "CANARYSUBJ", "CANARYFOLDER", "CANARYFILE"],
            "owner_dirs": sorted({e.owner_dir for e in self.org.custodians if e.owner_dir}),
            "display_names": sorted({e.display_name for e in self.org.everyone}),
            "bad_addresses": ["undisclosed-recipients:;"],
            "n_messages": len(self.messages),
            "n_files": len(self.files),
        }


def ts_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def finite(value: float) -> bool:
    return not (math.isnan(value) or math.isinf(value))
