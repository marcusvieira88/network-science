"""Rule N1 address normalisation and per-record recipient resolution (T026)."""

from __future__ import annotations

import pytest

from enron_case.clean.addresses import normalize_address, resolve_recipients


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("alice@example.com", "alice@example.com"),
        ("Alice.Smith@Example.COM", "alice.smith@example.com"),
        ("  bob@example.com\t", "bob@example.com"),
        ('"carol@example.com"', "carol@example.com"),
        ("'carol@example.com'", "carol@example.com"),
        ("<dave@example.com>", "dave@example.com"),
        ("mailto:erin@example.com", "erin@example.com"),
        ("MAILTO:erin@example.com", "erin@example.com"),
        ("<mailto:erin@example.com>", "erin@example.com"),
        (".frank@example.com.", "frank@example.com"),
        ("'.frank@example.com'", "frank@example.com"),
        ('" <Gina@Sub.Example.com> "', "gina@sub.example.com"),
    ],
)
def test_valid_addresses_normalise(raw: str, expected: str) -> None:
    assert normalize_address(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "undisclosed-recipients:;",
        "no at sign",
        "two@@example.com",
        "a@b@example.com",
        "user@localhost",
        "@example.com",
        "user@",
        "first last@example.com",
        "user@exa mple.com",
    ],
)
def test_malformed_addresses_are_invalid(raw: str) -> None:
    assert normalize_address(raw) is None


@pytest.mark.parametrize("raw", ["", "   ", '""', "<>", "mailto:", "."])
def test_empty_placeholders_are_invalid(raw: str) -> None:
    assert normalize_address(raw) is None


def test_recipients_unique_with_strongest_role() -> None:
    roles, bad = resolve_recipients(
        to=["B@example.com"],
        cc=["b@example.com", "a@example.com"],
        bcc=["a@example.com", "c@example.com"],
    )
    assert roles == {"a@example.com": "cc", "b@example.com": "to", "c@example.com": "bcc"}
    assert bad is False


def test_malformed_recipient_dropped_and_reported() -> None:
    roles, bad = resolve_recipients(to=["a@example.com", "undisclosed-recipients:;"], cc=[], bcc=[])
    assert roles == {"a@example.com": "to"}
    assert bad is True


def test_empty_placeholder_dropped_without_bad_flag() -> None:
    roles, bad = resolve_recipients(to=["", "  "], cc=["a@example.com"], bcc=[])
    assert roles == {"a@example.com": "cc"}
    assert bad is False
