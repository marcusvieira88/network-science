"""Deduplication without content, research R3 (T027)."""

from __future__ import annotations

import random
from datetime import UTC, datetime

import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from enron_case.clean.dedupe import Group, dedupe, groups_from_records, pairwise_scores
from enron_case.contracts import vocab as v
from enron_case.synth import SynthOutput

T0 = datetime(2001, 5, 1, 9, 30, 0, tzinfo=UTC)
T1 = datetime(2001, 5, 1, 9, 30, 1, tzinfo=UTC)
SENDER = "sam@example.com"


def copy(
    file_id: str,
    recipients: dict[str, str],
    *,
    sender: str | None = SENDER,
    ts: datetime | None = T0,
    owner: str = "owner-a",
    folder: str = "inbox",
    message_id: str | None = None,
) -> Group:
    return Group.single(
        file_id=file_id,
        owner=owner,
        folder_class=folder,
        sender=sender,
        ts_utc=ts,
        recipients=recipients,
        message_id=message_id,
        bad_address=False,
    )


def by_files(groups: list[Group]) -> dict[frozenset[str], Group]:
    return {g.file_ids: g for g in groups}


def test_single_copy_has_rule_none() -> None:
    [only] = dedupe([copy("f1", {"a@example.com": "to"})])
    assert only.rule == "none"
    assert only.n_copies == 1


def test_exact_copies_merge() -> None:
    out = dedupe(
        [
            copy("f1", {"a@example.com": "to"}, owner="sam", folder="sent"),
            copy("f2", {"a@example.com": "to"}, owner="ann"),
        ]
    )
    [merged] = out
    assert merged.rule == "exact"
    assert merged.n_copies == 2
    assert merged.owners == frozenset({"sam", "ann"})
    assert merged.sent_owner == "sam"


def test_different_second_does_not_merge() -> None:
    out = dedupe([copy("f1", {"a@example.com": "to"}), copy("f2", {"a@example.com": "to"}, ts=T1)])
    assert len(out) == 2
    assert {g.rule for g in out} == {"none"}


def test_subset_merges_into_union_with_bcc() -> None:
    sender_copy = copy("f1", {"a@example.com": "to", "z@example.com": "bcc"}, folder="sent")
    receiver_copy = copy("f2", {"a@example.com": "to"}, owner="ann")
    [merged] = dedupe([sender_copy, receiver_copy])
    assert merged.rule == "subset"
    assert merged.recipients == (("a@example.com", "to"), ("z@example.com", "bcc"))
    assert merged.n_copies == 2
    expected_key = v.msg_key(SENDER, T0, ["a@example.com", "z@example.com"])
    assert merged.key == expected_key


def test_subset_with_exact_members_counts_all_copies() -> None:
    out = dedupe(
        [
            copy("f1", {"a@example.com": "to", "b@example.com": "cc"}, folder="sent"),
            copy("f2", {"a@example.com": "to", "b@example.com": "cc"}, folder="sent"),
            copy("f3", {"a@example.com": "to"}),
            copy("f4", {"a@example.com": "to"}),
        ]
    )
    [merged] = out
    assert merged.rule == "subset"
    assert merged.n_copies == 4


def test_incomparable_sets_stay_apart() -> None:
    out = dedupe([copy("f1", {"a@example.com": "to"}), copy("f2", {"b@example.com": "to"})])
    assert len(out) == 2


def test_subset_of_two_incomparable_sets_joins_the_larger_only() -> None:
    small = copy("f1", {"a@example.com": "to"})
    big = copy("f2", {"a@example.com": "to", "b@example.com": "to", "c@example.com": "to"})
    other = copy("f3", {"a@example.com": "to", "d@example.com": "to"})
    groups = by_files(dedupe([small, big, other]))
    assert set(groups) == {frozenset({"f1", "f2"}), frozenset({"f3"})}
    assert groups[frozenset({"f1", "f2"})].rule == "subset"
    assert groups[frozenset({"f3"})].rule == "none"


def test_null_timestamp_merges_exactly_but_not_by_subset() -> None:
    out = dedupe(
        [
            copy("f1", {"a@example.com": "to"}, ts=None),
            copy("f2", {"a@example.com": "to"}, ts=None),
            copy("f3", {"a@example.com": "to", "b@example.com": "bcc"}, ts=None),
        ]
    )
    groups = by_files(out)
    assert set(groups) == {frozenset({"f1", "f2"}), frozenset({"f3"})}
    assert groups[frozenset({"f1", "f2"})].rule == "exact"
    assert groups[frozenset({"f1", "f2"})].key == v.msg_key(SENDER, None, ["a@example.com"])


def test_merge_keeps_strongest_role_across_copies() -> None:
    [merged] = dedupe(
        [
            copy("f1", {"a@example.com": "bcc", "b@example.com": "to"}, folder="sent"),
            copy("f2", {"a@example.com": "cc"}),
        ]
    )
    assert dict(merged.recipients)["a@example.com"] == "cc"


def test_records_resolve_roles_and_bad_addresses() -> None:
    records = pl.DataFrame(
        {
            "file_id": ["f1"],
            "mailbox_owner": ["ann"],
            "folder_class": ["inbox"],
            "ts_utc": [T0],
            "from_addr": ["Sam@Example.com"],
            "to_addrs": [["a@example.com", "undisclosed-recipients:;"]],
            "cc_addrs": [["A@example.com"]],
            "bcc_addrs": [[]],
            "message_id": ["<1.x>"],
        },
        schema_overrides={"bcc_addrs": pl.List(pl.String())},
    )
    [group] = groups_from_records(records)
    assert group.sender == SENDER
    assert group.recipients == (("a@example.com", "to"),)
    assert group.bad_address is True


def test_invalid_sender_becomes_null_and_bad() -> None:
    records = pl.DataFrame(
        {
            "file_id": ["f1"],
            "mailbox_owner": ["ann"],
            "folder_class": ["inbox"],
            "ts_utc": [T0],
            "from_addr": ["not an address"],
            "to_addrs": [["a@example.com"]],
            "cc_addrs": [[]],
            "bcc_addrs": [[]],
            "message_id": [None],
        },
        schema_overrides={
            "cc_addrs": pl.List(pl.String()),
            "bcc_addrs": pl.List(pl.String()),
            "message_id": pl.String(),
        },
    )
    [group] = groups_from_records(records)
    assert group.sender is None
    assert group.bad_address is True


# ---- pairwise precision / recall, hand-computed ---------------------------------------------


def test_pairwise_scores_hand_computed() -> None:
    truth = {"f1": "m1", "f2": "m1", "f3": "m1", "f4": "m2", "f5": "m2"}
    # predicted {f1,f2} {f3,f4,f5}: pairs (f1f2 ok) (f3f4 x) (f3f5 x) (f4f5 ok)
    predicted = [frozenset({"f1", "f2"}), frozenset({"f3", "f4", "f5"})]
    precision, recall = pairwise_scores(predicted, truth)
    assert precision == 2 / 4
    # true pairs: f1f2 f1f3 f2f3 f4f5 = 4, found 2
    assert recall == 2 / 4


def test_pairwise_scores_fail_on_a_file_without_truth() -> None:
    with pytest.raises(KeyError):
        pairwise_scores([frozenset({"f1", "f2"})], {"f1": "m1"})


def test_pairwise_scores_undefined_without_pairs() -> None:
    precision, recall = pairwise_scores([frozenset({"f1"})], {"f1": "m1"})
    assert precision is None
    assert recall is None


# ---- properties -------------------------------------------------------------------------------

ADDRS = ["a@example.com", "b@example.com", "c@example.com", "d@example.com"]
SENDERS = ["sam@example.com", "tom@example.com"]
TIMES = [T0, T1, None]

copy_strategy = st.builds(
    lambda sender, ts, recips, owner, folder: (sender, ts, recips, owner, folder),
    st.sampled_from(SENDERS),
    st.sampled_from(TIMES),
    st.dictionaries(st.sampled_from(ADDRS), st.sampled_from(v.RECIPIENT_ROLES), max_size=4),
    st.sampled_from(["ann", "bob", "cid"]),
    st.sampled_from(v.FOLDER_CLASSES),
)


def build(specs: list[tuple[str, datetime | None, dict[str, str], str, str]]) -> list[Group]:
    return [
        copy(f"f{i}", recips, sender=sender, ts=ts, owner=owner, folder=folder)
        for i, (sender, ts, recips, owner, folder) in enumerate(specs)
    ]


@settings(max_examples=200, deadline=None)
@given(st.lists(copy_strategy, max_size=12), st.randoms(use_true_random=False))
def test_dedupe_is_order_independent(
    specs: list[tuple[str, datetime | None, dict[str, str], str, str]], rng: random.Random
) -> None:
    groups = build(specs)
    shuffled = list(groups)
    rng.shuffle(shuffled)
    assert dedupe(groups) == dedupe(shuffled)


@settings(max_examples=200, deadline=None)
@given(st.lists(copy_strategy, max_size=12))
def test_dedupe_is_idempotent(
    specs: list[tuple[str, datetime | None, dict[str, str], str, str]],
) -> None:
    once = dedupe(build(specs))
    assert dedupe(once) == once


@settings(max_examples=200, deadline=None)
@given(st.lists(copy_strategy, max_size=12))
def test_dedupe_conserves_files_and_keys_are_unique(
    specs: list[tuple[str, datetime | None, dict[str, str], str, str]],
) -> None:
    out = dedupe(build(specs))
    files = [f for g in out for f in g.file_ids]
    assert sorted(files) == sorted(f"f{i}" for i in range(len(specs)))
    assert len({g.key for g in out}) == len(out)


# ---- ground truth --------------------------------------------------------------------------


def test_precision_and_recall_against_ground_truth(synth: SynthOutput) -> None:
    truth = {v.file_id(path): msg for path, msg in synth.truth()["file_to_message"].items()}
    out = dedupe(groups_from_records(synth.table("header_records")))
    precision, recall = pairwise_scores([g.file_ids for g in out], truth)
    assert precision is not None
    assert recall is not None
    assert precision >= 0.95
    print(f"dedupe precision={precision:.4f} recall={recall:.4f}")


def test_records_without_sender_are_never_merged() -> None:
    ts = datetime(2001, 5, 1, 10, 0, tzinfo=UTC)
    a = _single("f1", None, ts, {"r@x.com": "to"})
    b = _single("f2", None, ts, {"r@x.com": "to"})
    assert len(dedupe([a, b])) == 2


def test_empty_recipient_set_joins_only_an_unambiguous_host() -> None:
    ts = datetime(2001, 5, 1, 10, 0, tzinfo=UTC)
    empty = _single("f1", "s@x.com", ts, {})
    full = _single("f2", "s@x.com", ts, {"r@x.com": "to"})
    other = _single("f3", "s@x.com", ts, {"q@x.com": "to"})
    assert len(dedupe([empty, full])) == 1  # Bcc-only copy joins the one message it can
    assert len(dedupe([empty, full, other])) == 3  # two possible hosts: stays on its own


def _single(file_id: str, sender: str | None, ts: datetime, recipients: dict[str, str]) -> Group:
    return Group.single(
        file_id=file_id,
        owner="o",
        folder_class="inbox",
        sender=sender,
        ts_utc=ts,
        recipients=recipients,
        message_id=None,
        bad_address=sender is None,
    )
