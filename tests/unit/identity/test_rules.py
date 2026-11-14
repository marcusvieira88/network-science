"""T032: rules N2-N5 and guards, on hand-built cases and on the synthetic ground truth."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from enron_case.config import Config
from enron_case.identity import rules
from enron_case.identity.resolve import resolve
from enron_case.synth import SynthOutput
from helpers import ctx_with_fixtures

from .builders import BASE, headers, messages, sends

SUPPORT = Config().name_link_support


def accepted(candidates: list[rules.Candidate]) -> set[tuple[str, str, str]]:
    return {(c.left, c.right, c.rule) for c in candidates if c.guard is None}


def blocked(candidates: list[rules.Candidate]) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in candidates:
        if c.guard is not None:
            out[c.guard] = out.get(c.guard, 0) + 1
    return out


# ---- N1 helpers ---------------------------------------------------------------------------
def test_normalize_address() -> None:
    assert rules.normalize_address(" 'Kim.Lo@Org.COM' ") == "kim.lo@org.com"
    assert rules.normalize_address("<mailto:kim.lo@org.com>") == "kim.lo@org.com"


def test_normalize_name_handles_last_first_and_noise() -> None:
    assert rules.normalize_name('"Lo, Kim"') == "kim lo"
    assert rules.normalize_name("Kim  Lo <kim.lo@org.com>") == "kim lo"
    assert rules.normalize_name("Kim Lo (Legal)") == "kim lo"
    assert rules.normalize_name("kim.lo@org.com") is None
    assert rules.normalize_name("  ") is None
    assert rules.normalize_name(None) is None


def test_registered_domain_is_last_two_labels() -> None:
    assert rules.registered_domain("x@ect.org.com") == "org.com"
    assert rules.registered_domain("x@org.com") == "org.com"


# ---- N2 -------------------------------------------------------------------------------------
def test_n2_merges_same_local_part_under_one_registered_domain() -> None:
    found = rules.subdomain_candidates(["kim.lo@ect.org.com", "kim.lo@org.com", "kim.lo@other.com"])
    assert accepted(found) == {("kim.lo@ect.org.com", "kim.lo@org.com", "N2")}


def test_n2_never_uses_generic_local_parts() -> None:
    found = rules.subdomain_candidates(["info@ect.org.com", "info@org.com"])
    assert accepted(found) == set()
    assert blocked(found) == {rules.GUARD_GENERIC: 1}


# ---- N3 -------------------------------------------------------------------------------------
def name_links(rows: list[dict[str, object]]) -> list[rules.Candidate]:
    hdr = headers(rows)
    known = {str(r["from_addr"]) for r in rows}
    return rules.name_link_candidates(rules.sender_name_support(hdr, known), SUPPORT)


def test_n3_links_compatible_aliases_with_enough_support() -> None:
    rows = sends("kim.lo@org.com", "Kim Lo", SUPPORT) + sends("klo@org.com", "Lo, Kim", SUPPORT)
    assert accepted(name_links(rows)) == {("kim.lo@org.com", "klo@org.com", "N3")}


def test_n3_accepts_underscore_and_joined_forms() -> None:
    for alias in ("kim_lo@org.com", "kimlo@org.com"):
        rows = sends("kim.lo@org.com", "Kim Lo", SUPPORT) + sends(alias, "Kim Lo", SUPPORT)
        assert accepted(name_links(rows)) == {("kim.lo@org.com", alias, "N3")}


def test_n3_needs_support_on_both_addresses() -> None:
    rows = sends("kim.lo@org.com", "Kim Lo", SUPPORT) + sends("klo@org.com", "Kim Lo", SUPPORT - 1)
    assert name_links(rows) == []


def test_n3_counts_distinct_sends_not_file_copies() -> None:
    copies = [{"from_addr": "klo@org.com", "x_from": "Kim Lo"}] * SUPPORT
    hdr = headers(sends("kim.lo@org.com", "Kim Lo", SUPPORT)).vstack(
        headers(copies).with_columns(pl.lit(BASE).cast(pl.Datetime("us", "UTC")).alias("ts_utc"))
    )
    support = rules.sender_name_support(hdr, {"kim.lo@org.com", "klo@org.com"})
    assert support[("klo@org.com", "kim lo")] == 1


def test_guard_never_merges_on_name_alone() -> None:
    rows = sends("kim.lo@org.com", "Kim Lo", SUPPORT) + sends("trader7@org.com", "Kim Lo", SUPPORT)
    found = name_links(rows)
    assert accepted(found) == set()
    assert blocked(found) == {rules.GUARD_NAME_ONLY: 1}


def test_guard_never_merges_across_registered_domains() -> None:
    rows = sends("kim.lo@org.com", "Kim Lo", SUPPORT) + sends("klo@rival.com", "Kim Lo", SUPPORT)
    found = name_links(rows)
    assert accepted(found) == set()
    assert blocked(found) == {rules.GUARD_CROSS_ORG: 1}


def test_guard_excludes_generic_local_parts_from_n3() -> None:
    rows = sends("kim.lo@org.com", "Kim Lo", SUPPORT) + sends("support@org.com", "Kim Lo", SUPPORT)
    found = name_links(rows)
    assert accepted(found) == set()
    assert blocked(found) == {rules.GUARD_GENERIC: 1}


# ---- N4 -------------------------------------------------------------------------------------
def legacy_rows(pairs: list[tuple[str, str]], times: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for legacy, addr in pairs:
        for _ in range(times):
            rows.append(
                {
                    "from_addr": "boss@org.com",
                    "x_from": "Boss",
                    "to_addrs": ["peer@org.com", addr],
                    "x_to": f"Peer Person, {legacy}",
                }
            )
    return rows


def test_n4_links_legacy_form_paired_at_the_same_position() -> None:
    rows = legacy_rows([("Kim Lo/HOU/ECT", "kim.lo@org.com")], SUPPORT)
    found = rules.legacy_candidates(headers(rows), {"kim.lo@org.com", "peer@org.com"}, SUPPORT)
    assert accepted(found) == {("kim lo/hou/ect", "kim.lo@org.com", "N4")}


def test_n4_needs_support_and_ignores_misaligned_lists() -> None:
    rows = legacy_rows([("Kim Lo/HOU/ECT", "kim.lo@org.com")], SUPPORT - 1)
    rows.append({"from_addr": "boss@org.com", "to_addrs": ["kim.lo@org.com"], "x_to": "A, Kim Lo/HOU/ECT"})
    found = rules.legacy_candidates(headers(rows), {"kim.lo@org.com", "peer@org.com"}, SUPPORT)
    assert found == []


def test_n4_blocks_a_legacy_form_paired_with_two_addresses() -> None:
    rows = legacy_rows([("Kim Lo/HOU/ECT", "kim.lo@org.com"), ("Kim Lo/HOU/ECT", "kl@org.com")], SUPPORT)
    known = {"kim.lo@org.com", "kl@org.com", "peer@org.com"}
    found = rules.legacy_candidates(headers(rows), known, SUPPORT)
    assert accepted(found) == set()
    assert set(blocked(found)) == {rules.GUARD_AMBIGUOUS_LEGACY}


def test_n4_attaches_legacy_form_to_the_entity_with_its_support() -> None:
    rows = legacy_rows([("Kim Lo/HOU/ECT", "kim.lo@org.com")], SUPPORT)
    occurrences = {"kim.lo@org.com": 7, "peer@org.com": 3}
    found = rules.legacy_candidates(headers(rows), set(occurrences), SUPPORT)
    amap = resolve(occurrences, found).address_map
    row = amap.filter(pl.col("addr") == "kim lo/hou/ect").row(0, named=True)
    assert row == {"addr": "kim lo/hou/ect", "entity_id": "kim.lo@org.com", "rule": "N4", "support": SUPPORT}


# ---- N5 -------------------------------------------------------------------------------------
def test_n5_marks_dominant_sent_address_per_owner() -> None:
    msgs = messages(
        [("kim.lo@org.com", ["a@org.com"])] * 3 + [("klo@org.com", ["a@org.com"])] + [("a@org.com", ["kim.lo@org.com"])],
        sent_owner={0: "lo-k", 1: "lo-k", 2: "lo-k", 3: "lo-k"},
    )
    assert rules.custodian_addresses(msgs) == {"kim.lo@org.com"}


def test_n5_breaks_ties_by_smallest_address() -> None:
    msgs = messages([("b@org.com", ["c@org.com"]), ("a@org.com", ["c@org.com"])], sent_owner={0: "x", 1: "x"})
    assert rules.custodian_addresses(msgs) == {"a@org.com"}


# ---- synthetic ground truth -----------------------------------------------------------------
def synth_candidates(synth: SynthOutput, tmp_path: Path) -> list[rules.Candidate]:
    ctx = ctx_with_fixtures("identity", synth, tmp_path, tables=("messages", "header_records"))
    return rules.evidence(ctx.read("messages"), ctx.read("header_records"), SUPPORT)


def test_rules_merge_every_supported_ground_truth_alias(synth: SynthOutput, tmp_path: Path) -> None:
    truth = synth.truth()
    msgs = synth.table("messages")
    occurrences = rules.address_occurrences(msgs)
    sent = msgs.group_by("sender_addr").len()
    sent_count = dict(zip(sent["sender_addr"].to_list(), sent["len"].to_list(), strict=True))
    entity_of = dict(resolve(occurrences, synth_candidates(synth, tmp_path)).address_map.select("addr", "entity_id").iter_rows())
    checked = 0
    for entity in truth["entities"]:
        observed = [a for a in entity["addresses"] if a in occurrences]
        primary = entity["addresses"][0]
        for alias in observed[1:]:
            subdomain = rules.local_part(alias) == rules.local_part(primary)
            supported = subdomain or min(sent_count.get(alias, 0), sent_count.get(primary, 0)) >= SUPPORT
            if supported:
                checked += 1
                assert entity_of[alias] == entity_of[primary], entity["truth_id"]
    assert checked >= 20


def test_homonym_stays_separate(synth: SynthOutput, tmp_path: Path) -> None:
    truth = synth.truth()
    homonym = next(e for e in truth["entities"] if e["truth_id"] == "X900")
    twin = next(
        e for e in truth["entities"]
        if e["display_name"] == homonym["display_name"] and e["truth_id"] != "X900"
    )
    candidates = synth_candidates(synth, tmp_path)
    occurrences = rules.address_occurrences(synth.table("messages"))
    resolution = resolve(occurrences, candidates)
    entity_of = dict(resolution.address_map.select("addr", "entity_id").iter_rows())
    assert entity_of[homonym["addresses"][0]] != entity_of[twin["addresses"][0]]
    assert resolution.blocked_by_guard.get(rules.GUARD_CROSS_ORG, 0) >= 1
