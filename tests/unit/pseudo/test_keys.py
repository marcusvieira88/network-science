"""T038: key resolution, safety checks, subkeys and fingerprint (contracts/cli.md)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from enron_case import config
from enron_case.cli import load_key_fingerprint
from enron_case.errors import KeyProblem
from enron_case.pseudo import keys
from helpers import TEST_KEY_HEX

OTHER_KEY_HEX = "ab" * 32
# HMAC-SHA256(TEST_KEY, b"fingerprint-v1"), first 8 hex chars, computed once by hand.
TEST_KEY_FINGERPRINT = "f541f77c"


@pytest.fixture
def no_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """No key in the environment and an empty home directory. Returns the home directory."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.delenv(config.KEY_ENV, raising=False)
    monkeypatch.delenv(config.KEY_FILE_ENV, raising=False)
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


def write_key(path: Path, hex_text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(hex_text + "\n", encoding="utf-8")
    path.chmod(0o600)  # as scripts/create-key.sh writes it
    return path


def test_environment_key_is_used(no_key: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(config.KEY_ENV, TEST_KEY_HEX)
    assert keys.load_key() == bytes.fromhex(TEST_KEY_HEX)


def test_environment_beats_key_file(
    no_key: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path
) -> None:
    monkeypatch.setenv(config.KEY_ENV, TEST_KEY_HEX)
    monkeypatch.setenv(config.KEY_FILE_ENV, str(write_key(tmp_path / "k", OTHER_KEY_HEX)))
    assert keys.load_key(repo) == bytes.fromhex(TEST_KEY_HEX)


def test_key_file_variable_beats_default_file(
    no_key: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path
) -> None:
    write_key(no_key / config.DEFAULT_KEY_PATH, TEST_KEY_HEX)
    monkeypatch.setenv(config.KEY_FILE_ENV, str(write_key(tmp_path / "k", OTHER_KEY_HEX)))
    assert keys.load_key(repo) == bytes.fromhex(OTHER_KEY_HEX)


def test_default_file_in_home(no_key: Path, repo: Path) -> None:
    write_key(no_key / ".config" / "enron-case" / "key", OTHER_KEY_HEX)
    assert keys.load_key(repo) == bytes.fromhex(OTHER_KEY_HEX)


def test_missing_key_exits_3(no_key: Path, repo: Path) -> None:
    with pytest.raises(KeyProblem) as info:
        keys.load_key(repo)
    assert info.value.exit_code == 3


def test_missing_named_key_file_does_not_fall_through(
    no_key: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path
) -> None:
    write_key(no_key / config.DEFAULT_KEY_PATH, TEST_KEY_HEX)
    monkeypatch.setenv(config.KEY_FILE_ENV, str(tmp_path / "absent"))
    with pytest.raises(KeyProblem):
        keys.load_key(repo)


@pytest.mark.parametrize("bad_hex", ["ab" * 31, "ab" * 16, "", "zz" * 32])
def test_short_or_malformed_environment_key_exits_3(
    no_key: Path, monkeypatch: pytest.MonkeyPatch, bad_hex: str
) -> None:
    monkeypatch.setenv(config.KEY_ENV, bad_hex)
    with pytest.raises(KeyProblem):
        keys.load_key()


def test_short_key_file_exits_3(
    no_key: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path
) -> None:
    monkeypatch.setenv(config.KEY_FILE_ENV, str(write_key(tmp_path / "k", "ab" * 31)))
    with pytest.raises(KeyProblem):
        keys.load_key(repo)


def test_key_file_inside_repository_exits_3(
    no_key: Path, monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    monkeypatch.setenv(config.KEY_FILE_ENV, str(write_key(repo / "secrets" / "key", TEST_KEY_HEX)))
    with pytest.raises(KeyProblem):
        keys.load_key(repo)


def test_symlink_resolving_inside_repository_exits_3(
    no_key: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path
) -> None:
    target = write_key(repo / "key", TEST_KEY_HEX)
    link = tmp_path / "outside-link"
    link.symlink_to(target)
    monkeypatch.setenv(config.KEY_FILE_ENV, str(link))
    with pytest.raises(KeyProblem):
        keys.load_key(repo)


def test_default_home_inside_repository_exits_3(no_key: Path) -> None:
    write_key(no_key / config.DEFAULT_KEY_PATH, TEST_KEY_HEX)
    with pytest.raises(KeyProblem):
        keys.load_key(no_key)


def test_error_messages_never_contain_the_key(
    no_key: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path
) -> None:
    short_hex = "c0ffee" * 10  # 30 bytes: too short
    monkeypatch.setenv(config.KEY_ENV, short_hex)
    with pytest.raises(KeyProblem) as from_env:
        keys.load_key(repo)
    monkeypatch.delenv(config.KEY_ENV)
    monkeypatch.setenv(config.KEY_FILE_ENV, str(write_key(repo / "k", TEST_KEY_HEX)))
    with pytest.raises(KeyProblem) as from_file:
        keys.load_key(repo)
    for message in (str(from_env.value), str(from_file.value)):
        assert short_hex not in message
        assert TEST_KEY_HEX not in message


def test_fingerprint_known_answer() -> None:
    assert keys.key_fingerprint(bytes.fromhex(TEST_KEY_HEX)) == TEST_KEY_FINGERPRINT


def test_fingerprint_differs_by_key_and_is_not_the_key() -> None:
    first = keys.key_fingerprint(bytes.fromhex(TEST_KEY_HEX))
    second = keys.key_fingerprint(bytes.fromhex(OTHER_KEY_HEX))
    assert first != second
    assert first not in TEST_KEY_HEX


def test_subkeys_differ_per_label_and_are_stable() -> None:
    key = bytes.fromhex(TEST_KEY_HEX)
    derived = [keys.subkey(key, label) for label in keys.SUBKEY_LABELS]
    assert len(set(derived)) == len(keys.SUBKEY_LABELS) == 3
    assert key not in derived
    assert keys.subkey(key, keys.PERSON_LABEL) == derived[0]
    assert keys.subkey(bytes.fromhex(OTHER_KEY_HEX), keys.PERSON_LABEL) != derived[0]


def test_unknown_subkey_label_is_refused() -> None:
    with pytest.raises(KeyProblem):
        keys.subkey(bytes.fromhex(TEST_KEY_HEX), "person-v2")


def test_orchestrator_records_only_the_fingerprint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(config.KEY_ENV, TEST_KEY_HEX)
    recorded = load_key_fingerprint(sample=True)
    assert recorded == TEST_KEY_FINGERPRINT
    out = capsys.readouterr()
    assert TEST_KEY_HEX not in out.out + out.err
    assert TEST_KEY_HEX not in json.dumps({"key_fingerprint": recorded})


def test_real_run_refuses_the_published_sample_key(
    no_key: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(config.KEY_ENV, TEST_KEY_HEX)
    assert keys.load_run_key(sample=True, repo_root=repo) == bytes.fromhex(TEST_KEY_HEX)
    with pytest.raises(KeyProblem) as raised:
        keys.load_run_key(sample=False, repo_root=repo)
    assert raised.value.exit_code == 3
    assert TEST_KEY_HEX not in str(raised.value)
    with pytest.raises(KeyProblem):
        load_key_fingerprint(sample=False)


def test_real_run_accepts_a_private_key(
    no_key: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(config.KEY_ENV, OTHER_KEY_HEX)
    assert keys.load_run_key(sample=False, repo_root=repo) == bytes.fromhex(OTHER_KEY_HEX)


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o644, 0o660])
def test_key_file_readable_by_others_exits_3(
    no_key: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path, mode: int
) -> None:
    key_file = write_key(tmp_path / "k", OTHER_KEY_HEX)
    key_file.chmod(mode)
    monkeypatch.setenv(config.KEY_FILE_ENV, str(key_file))
    with pytest.raises(KeyProblem) as info:
        keys.load_key(repo)
    assert info.value.exit_code == 3
    assert OTHER_KEY_HEX not in str(info.value)


def test_owner_only_key_file_is_accepted(
    no_key: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path
) -> None:
    key_file = write_key(tmp_path / "k", OTHER_KEY_HEX)
    key_file.chmod(0o400)
    monkeypatch.setenv(config.KEY_FILE_ENV, str(key_file))
    assert keys.load_key(repo) == bytes.fromhex(OTHER_KEY_HEX)
