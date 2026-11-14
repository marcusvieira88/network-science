"""T039: keyed pseudonyms, the events and entities_p tables, and the stage."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from enron_case.context import StageContext
from enron_case.contracts import schemas
from enron_case.contracts import vocab as v
from enron_case.errors import ContractViolation, PseudonymCollision
from enron_case.pseudo import keys, pseudonymize, stage
from enron_case.synth import SynthOutput
from enron_case.synth.fixtures import FIXTURE_KEY
from enron_case.zones import Zone
from helpers import TEST_KEY_HEX, ctx_with_fixtures, scan

KEY = bytes.fromhex(TEST_KEY_HEX)
OTHER_KEY = bytes.fromhex("ab" * 32)
INPUTS = ("messages", "entities", "address_map")


# ---- pseudonym functions --------------------------------------------------------------------
def test_same_key_and_id_give_same_pid() -> None:
    assert pseudonymize.person_pid(KEY, "a.b@x.com") == pseudonymize.person_pid(KEY, "a.b@x.com")


def test_pid_formats() -> None:
    assert re.fullmatch(v.PSEUDONYM_PATTERN, pseudonymize.person_pid(KEY, "a@x.com"))
    assert re.fullmatch(v.ORG_PSEUDONYM_PATTERN, pseudonymize.org_pid(KEY, "x.com"))


def test_person_and_org_pids_use_separate_subkeys() -> None:
    person = pseudonymize.person_pid(KEY, "x.com")
    org = pseudonymize.org_pid(KEY, "x.com")
    assert person.removeprefix(v.PERSON_PREFIX) != org.removeprefix(v.ORG_PREFIX)


def test_scheme_matches_fixture_reference(synth: SynthOutput) -> None:
    """The fixture builds pids with the scheme of research R5 under its own key; with that key
    our functions must reproduce every fixture pid exactly."""
    entities = synth.table("entities")
    ours = sorted(pseudonymize.person_pid(FIXTURE_KEY, e) for e in entities["entity_id"])
    assert ours == sorted(synth.table("entities_p")["pid"].to_list())


def test_different_key_gives_disjoint_pids(synth: SynthOutput) -> None:
    ids = synth.table("entities")["entity_id"].to_list()
    first = {pseudonymize.person_pid(KEY, e) for e in ids}
    second = {pseudonymize.person_pid(OTHER_KEY, e) for e in ids}
    assert len(first) == len(second) == len(ids)
    assert first.isdisjoint(second)


def test_forced_collision_aborts_with_exit_7(
    synth: SynthOutput, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pseudonymize, "person_pid", lambda _k, _e: "p_" + "a" * 16)
    with pytest.raises(PseudonymCollision) as info:
        pseudonymize.build_entities_p(KEY, synth.table("entities"))
    assert info.value.exit_code == 7


def test_collision_message_names_no_identifier() -> None:
    with pytest.raises(PseudonymCollision) as info:
        pseudonymize.assert_unique(["a@x.com", "b@x.com"], ["p_same", "p_same"], "person")
    assert "@" not in str(info.value)


# ---- hand-built cases -----------------------------------------------------------------------
def tiny_inputs(
    ts: datetime | None = datetime(2001, 5, 1, 10, 59, 59, tzinfo=UTC),
    sender: str | None = "s@x.com",
    flags: tuple[str, ...] = (),
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    recipients = [
        {"addr": "r1@x.com", "role": "to"},
        {"addr": "r2@x.com", "role": "cc"},
        {"addr": "r3@y.org", "role": "bcc"},
        {"addr": "r1.alias@x.com", "role": "to"},
    ]
    messages = pl.DataFrame(
        {
            "msg_key": ["0123456789abcdef0123"],
            "ts_utc": [ts],
            "sender_addr": [sender],
            "recipients": [recipients],
            "n_recipients": [4],
            "n_copies": [1],
            "dedupe_rule": ["none"],
            "owner_copies": [[]],
            "sent_copy_owner": [None],
            "flags": [list(flags)],
        },
        schema=schemas.table("messages").polars_schema,
    )
    entities = pl.DataFrame(
        {
            "entity_id": ["r1@x.com", "r2@x.com", "r3@y.org", "s@x.com"],
            "type": ["person", "list", "person", "person"],
            "org_domain": ["x.com", "x.com", "y.org", "x.com"],
            "is_internal": [True, True, False, True],
            "is_custodian": [False, False, False, True],
            "n_addresses": [2, 1, 1, 1],
        },
        schema=schemas.table("entities").polars_schema,
    )
    address_map = pl.DataFrame(
        {
            "addr": ["r1.alias@x.com", "r1@x.com", "r2@x.com", "r3@y.org", "s@x.com"],
            "entity_id": ["r1@x.com", "r1@x.com", "r2@x.com", "r3@y.org", "s@x.com"],
            "rule": ["N3", None, None, None, None],
            "support": [1, 1, 1, 1, 1],
        },
        schema=schemas.table("address_map").polars_schema,
    )
    return messages, entities, address_map


def tiny_events(**kwargs: object) -> pl.DataFrame:
    return pseudonymize.build_events(KEY, *tiny_inputs(**kwargs))  # type: ignore[arg-type]


def test_one_event_per_recipient_entity_with_weight_and_hour() -> None:
    # Four addresses, three entities: r1@x.com and r1.alias@x.com are one person.
    events = tiny_events()
    assert events.height == 3
    assert events["weight"].to_list() == [1 / 3] * 3
    assert events["n_recipients"].to_list() == [3] * 3
    assert set(events["ts_hour"].to_list()) == {datetime(2001, 5, 1, 10, tzinfo=UTC)}
    assert events["in_network"].all()
    assert events["msg_pid"].n_unique() == 1
    assert events["event_id"].n_unique() == 3


def test_recipients_resolve_through_address_map() -> None:
    events = tiny_events()
    r1 = pseudonymize.person_pid(KEY, "r1@x.com")
    assert events.filter(pl.col("recipient_pid") == r1).height == 1
    assert events["sender_pid"].unique().to_list() == [pseudonymize.person_pid(KEY, "s@x.com")]
    r3 = events.filter(pl.col("role") == "bcc").row(0, named=True)
    assert r3["recipient_internal"] is False
    assert r3["recipient_org_pid"] == pseudonymize.org_pid(KEY, "y.org")
    assert events.filter(pl.col("role") == "cc")["recipient_type"].to_list() == ["list"]


def test_event_ids_follow_the_scheme() -> None:
    events = tiny_events()
    expected_msg = v.format_pseudonym(
        v.MESSAGE_PREFIX, keys.keyed_digest(KEY, keys.EVENT_LABEL, "0123456789abcdef0123")
    )
    expected_event = v.format_pseudonym(
        v.EVENT_PREFIX,
        keys.keyed_digest(KEY, keys.EVENT_LABEL, "0123456789abcdef0123|r2@x.com"),
    )
    assert events["msg_pid"].unique().to_list() == [expected_msg]
    assert expected_event in events["event_id"].to_list()


@pytest.mark.parametrize(
    "flag", ["date_out_of_range", "no_recipients", "self_only", "mass_mailing"]
)
def test_exclusion_flags_clear_in_network(flag: str) -> None:
    assert not tiny_events(flags=(flag,))["in_network"].any()


def test_bad_address_flag_alone_keeps_in_network() -> None:
    assert tiny_events(flags=("bad_address",))["in_network"].all()


def test_messages_without_time_or_sender_give_no_events() -> None:
    assert tiny_events(ts=None).height == 0
    assert tiny_events(sender=None).height == 0


def test_unmapped_address_fails_loudly() -> None:
    messages, entities, address_map = tiny_inputs()
    with pytest.raises(ContractViolation) as info:
        pseudonymize.build_events(KEY, messages, entities, address_map.slice(1))
    assert "@" not in str(info.value)


def test_address_mapped_twice_fails_loudly() -> None:
    messages, entities, address_map = tiny_inputs()
    doubled = pl.concat([address_map, address_map.slice(0, 1)])
    with pytest.raises(ContractViolation):
        pseudonymize.build_events(KEY, messages, entities, doubled)


def test_no_address_in_event_columns() -> None:
    assert schemas.leak_count(tiny_events(), (r"@",)) == 0


# ---- the stage on fixture inputs ------------------------------------------------------------
def run_stage(
    synth: SynthOutput, root: Path, monkeypatch: pytest.MonkeyPatch, key: bytes
) -> tuple[StageContext, list[str]]:
    monkeypatch.setenv(keys.KEY_ENV, key.hex())
    logs: list[str] = []
    ctx = ctx_with_fixtures("pseudo", synth, root, tables=INPUTS)
    ctx.log = logs.append
    stage.run(ctx)
    return ctx, logs


def test_stage_reproduces_fixture_under_fixture_key(
    synth: SynthOutput, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, _ = run_stage(synth, tmp_path, monkeypatch, FIXTURE_KEY)
    assert ctx.read("events").equals(synth.table("events"))
    assert ctx.read("entities_p").equals(synth.table("entities_p"))
    assert ctx.read_counts("pseudo_counts") == synth.counts("pseudo_counts")


def test_stage_matches_fixture_aggregates_under_test_key(
    synth: SynthOutput, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, _ = run_stage(synth, tmp_path, monkeypatch, KEY)
    events, reference = ctx.read("events"), synth.table("events")
    assert events.height == reference.height
    assert events["in_network"].sum() == reference["in_network"].sum()
    assert sorted(events["weight"].to_list()) == sorted(reference["weight"].to_list())
    entities_p = ctx.read("entities_p")
    assert entities_p["pid"].n_unique() == synth.table("entities").height
    assert set(entities_p["pid"]).isdisjoint(set(synth.table("entities_p")["pid"]))


def test_same_key_same_fingerprint_other_key_same_counts(
    synth: SynthOutput, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, _ = run_stage(synth, tmp_path / "a", monkeypatch, KEY)
    again, _ = run_stage(synth, tmp_path / "b", monkeypatch, KEY)
    other, _ = run_stage(synth, tmp_path / "c", monkeypatch, OTHER_KEY)
    assert first.outputs["events"] == again.outputs["events"]
    assert first.outputs["entities_p"] == again.outputs["entities_p"]
    assert first.outputs["events"] != other.outputs["events"]
    assert first.read_counts("pseudo_counts") == other.read_counts("pseudo_counts")
    assert set(first.read("events")["sender_pid"]).isdisjoint(
        set(other.read("events")["sender_pid"])
    )


def test_stage_writes_no_identifier_no_key_and_no_mapping(
    synth: SynthOutput, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, log_lines = run_stage(synth, tmp_path, monkeypatch, KEY)
    restricted = ctx.paths.dir(Zone.RESTRICTED)
    files = sorted(p.name for p in restricted.iterdir() if p.is_file())
    assert files == ["entities_p.parquet", "events.parquet"]
    needles = ["@", TEST_KEY_HEX, *synth.truth()["display_names"]]
    for zone in (Zone.RESTRICTED, Zone.COUNTS):
        assert scan(ctx.paths.dir(zone), needles) == {}
    logs = "\n".join(log_lines)
    assert logs
    assert "@" not in logs
    assert TEST_KEY_HEX not in logs
    for table in ("events", "entities_p"):
        assert not any("entity_id" in c or "addr" in c for c in ctx.read(table).columns)


def test_alias_of_the_sender_is_not_a_tie() -> None:
    """A message from s@x.com to its own alias and to r2: the alias is dropped (no self-loop)
    and the remaining recipient carries the full weight."""
    messages, entities, address_map = tiny_inputs()
    messages = messages.with_columns(
        pl.Series(
            "recipients",
            [[{"addr": "r1.alias@x.com", "role": "to"}, {"addr": "r2@x.com", "role": "to"}]],
        )
    )
    sender_alias = address_map.with_columns(
        pl.when(pl.col("addr") == "r1.alias@x.com")
        .then(pl.lit("s@x.com"))
        .otherwise(pl.col("entity_id"))
        .alias("entity_id")
    )
    events = pseudonymize.build_events(KEY, messages, entities, sender_alias)
    assert events.height == 1
    assert events["weight"].to_list() == [1.0]
    assert (events["sender_pid"] != events["recipient_pid"]).all()
