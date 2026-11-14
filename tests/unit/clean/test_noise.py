"""Noise flags and the research R3 Message-ID diagnostic (T030)."""

from __future__ import annotations

from datetime import UTC, datetime

from enron_case.clean.dedupe import Group, exact_pass
from enron_case.clean.noise import message_flags, message_id_shared_share
from enron_case.config import Config

T0 = datetime(2001, 5, 1, 9, 30, 0, tzinfo=UTC)
SENDER = "sam@example.com"
CONFIG = Config(recipient_cap=3)


def group(
    recipients: dict[str, str],
    *,
    file_id: str = "f1",
    ts: datetime | None = T0,
    bad: bool = False,
    message_id: str | None = None,
) -> Group:
    return Group.single(
        file_id=file_id,
        owner="ann",
        folder_class="inbox",
        sender=SENDER,
        ts_utc=ts,
        recipients=recipients,
        message_id=message_id,
        bad_address=bad,
    )


def test_clean_message_has_no_flags() -> None:
    assert message_flags(group({"a@example.com": "to"}), CONFIG) == []


def test_no_recipients() -> None:
    assert message_flags(group({}), CONFIG) == ["no_recipients"]


def test_self_only() -> None:
    assert message_flags(group({SENDER: "to"}), CONFIG) == ["self_only"]


def test_sender_among_others_is_not_self_only() -> None:
    assert message_flags(group({SENDER: "to", "a@example.com": "cc"}), CONFIG) == []


def test_mass_mailing_above_cap_only() -> None:
    at_cap = {f"r{i}@example.com": "to" for i in range(3)}
    above = {f"r{i}@example.com": "to" for i in range(4)}
    assert message_flags(group(at_cap), CONFIG) == []
    assert message_flags(group(above), CONFIG) == ["mass_mailing"]


def test_date_out_of_range_and_bad_address_sorted() -> None:
    old = datetime(1980, 1, 1, tzinfo=UTC)
    flags = message_flags(group({"a@example.com": "to"}, ts=old, bad=True), CONFIG)
    assert flags == ["bad_address", "date_out_of_range"]


def test_message_id_share_counts_exact_groups_only() -> None:
    copies = [
        # exact group sharing one id
        group({"a@example.com": "to"}, file_id="f1", message_id="<1>"),
        group({"a@example.com": "to"}, file_id="f2", message_id="<1>"),
        # exact group with different ids
        group({"b@example.com": "to"}, file_id="f3", message_id="<2>"),
        group({"b@example.com": "to"}, file_id="f4", message_id="<3>"),
        # exact group with one id missing
        group({"c@example.com": "to"}, file_id="f5", message_id="<4>"),
        group({"c@example.com": "to"}, file_id="f6", message_id=None),
        # single copy: not an exact-duplicate group
        group({"d@example.com": "to"}, file_id="f7", message_id="<5>"),
    ]
    assert message_id_shared_share(exact_pass(copies)) == 1 / 3


def test_message_id_share_undefined_without_duplicates() -> None:
    assert message_id_shared_share(exact_pass([group({"a@example.com": "to"})])) is None
