"""T033: entity typing by documented patterns and behaviour."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from enron_case.config import Config
from enron_case.contracts import schemas, vocab
from enron_case.identity import classify, stage
from enron_case.synth import SynthOutput
from helpers import ctx_with_fixtures

from .builders import messages

CAP = Config().recipient_cap
ROLE_MIN_MASS_SENDS = Config().role_min_mass_sends


def test_patterns() -> None:
    assert classify.pattern_type("mailer-daemon") == "system"
    assert classify.pattern_type("postmaster") == "system"
    assert classify.pattern_type("no.address") == "system"
    assert classify.pattern_type("announcements") == "role"
    assert classify.pattern_type("info") == "role"
    assert classify.pattern_type("all.traders") == "list"
    assert classify.pattern_type("gas.desk") == "list"
    assert classify.pattern_type("kim.lo") is None
    assert classify.pattern_type("desktop.support.lead") is None


def behaviour_of(rows: list[tuple[str, list[str]]]) -> dict[str, classify.Behaviour]:
    msgs = messages(rows)
    addrs = {a for sender, recipients in rows for a in (sender, *recipients)}
    return classify.entity_behaviour(msgs, {a: a for a in addrs}, CAP)


def test_never_sending_is_not_enough_to_be_a_list() -> None:
    """Only about 150 mailboxes were collected, so most real people never appear as a sender.
    Behaviour alone must not turn them into lists; only list-like address patterns do."""
    senders = [f"s{i}@org.com" for i in range(25)]
    beh = behaviour_of([(s, ["jane.doe@org.com"]) for s in senders])
    assert (
        classify.entity_type(["jane.doe@org.com"], beh["jane.doe@org.com"], ROLE_MIN_MASS_SENDS)
        == "person"
    )


def test_mass_sender_more_than_once_is_a_role() -> None:
    many = [f"r{i}@org.com" for i in range(CAP + 1)]
    beh = behaviour_of([("blast@org.com", many)] * 2)
    assert (
        classify.entity_type(["blast@org.com"], beh["blast@org.com"], ROLE_MIN_MASS_SENDS) == "role"
    )
    once = behaviour_of([("blast@org.com", many)])
    assert (
        classify.entity_type(["blast@org.com"], once["blast@org.com"], ROLE_MIN_MASS_SENDS)
        == "person"
    )


def test_patterns_take_precedence_over_behaviour() -> None:
    many = [f"r{i}@org.com" for i in range(CAP + 1)]
    beh = behaviour_of([("mailer-daemon@org.com", many)] * 2)
    assert (
        classify.entity_type(
            ["mailer-daemon@org.com"], beh["mailer-daemon@org.com"], ROLE_MIN_MASS_SENDS
        )
        == "system"
    )


def test_behaviour_counts_mass_sends_per_entity() -> None:
    # Two aliases of one entity each send one message above the cap, and one below it:
    # the entity has 2 mass sends; a recipient-only entity has none.
    many = [f"r{i}@org.com" for i in range(CAP + 1)]
    msgs = messages([("a@org.com", many), ("a2@org.com", many), ("a@org.com", ["l@org.com"])])
    entity_of = {"a@org.com": "a@org.com", "a2@org.com": "a@org.com", "l@org.com": "l@org.com"}
    beh = classify.entity_behaviour(msgs, entity_of, CAP)
    assert beh["a@org.com"].mass_sends == 2
    assert beh["l@org.com"].mass_sends == 0


def test_types_on_synthetic_corpus(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("identity", synth, tmp_path, tables=("messages", "header_records"))
    stage.run(ctx)
    ours = ctx.read("entities")
    assert set(ours["type"].to_list()) <= set(vocab.ENTITY_TYPES)
    ref = synth.table("entities").select("entity_id", pl.col("type").alias("ref"))
    joined = ours.join(ref, on="entity_id")
    assert joined.height == ours.height
    assert joined.filter(pl.col("type") != pl.col("ref")).height == 0


def test_custodian_flag_only_via_n5(synth: SynthOutput, tmp_path: Path) -> None:
    ctx = ctx_with_fixtures("identity", synth, tmp_path, tables=("messages", "header_records"))
    spec = schemas.table("messages")
    spec_path = ctx.paths.dir(spec.zone) / spec.filename
    pl.read_parquet(spec_path).with_columns(
        pl.lit(None, pl.String).alias("sent_copy_owner")
    ).write_parquet(spec_path)
    stage.run(ctx)
    assert not ctx.read("entities")["is_custodian"].any()

    truth = {e["entity_id"] for e in synth.truth()["entities"] if e["is_custodian"]}
    full = ctx_with_fixtures(
        "identity", synth, tmp_path / "b", tables=("messages", "header_records")
    )
    stage.run(full)
    flagged = set(full.read("entities").filter(pl.col("is_custodian"))["entity_id"].to_list())
    assert flagged == truth
