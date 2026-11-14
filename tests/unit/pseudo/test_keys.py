"""T038: key resolution, safety checks, subkeys and fingerprint (contracts/cli.md)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from enron_case import config
from enron_case.cli import load_key_fingerprint
from enron_case.errors import KeyProblem
from enron_case.pseudo import keys
from helpers import TEST_KEY_HEX

OTHER_KEY_HEX = "ab" * 32
POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits; Windows uses ACLs")
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
    monkeypatch.setenv("USERPROFILE", str(home))  # Path.home() on Windows
    return home


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


def write_key(path: Path, hex_text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(hex_text + "\n", encoding="utf-8")
    path.chmod(0o600)  # as keys.create_key_file writes it
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
    try:
        link.symlink_to(target)
    except OSError:  # Windows without the symlink privilege
        pytest.skip("this account may not create symbolic links")
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
    """The POSIX check. On a Windows runner the file reports 0o666, which it also refuses."""
    monkeypatch.setattr(keys, "ON_WINDOWS", False)
    key_file = write_key(tmp_path / "k", OTHER_KEY_HEX)
    key_file.chmod(mode)
    monkeypatch.setenv(config.KEY_FILE_ENV, str(key_file))
    with pytest.raises(KeyProblem) as info:
        keys.load_key(repo)
    assert info.value.exit_code == 3
    assert OTHER_KEY_HEX not in str(info.value)


@POSIX_ONLY
@pytest.mark.parametrize("mode", [0o400, 0o600])
def test_owner_only_key_file_is_accepted(
    no_key: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path, mode: int
) -> None:
    key_file = write_key(tmp_path / "k", OTHER_KEY_HEX)
    key_file.chmod(mode)
    monkeypatch.setenv(config.KEY_FILE_ENV, str(key_file))
    assert keys.load_key(repo) == bytes.fromhex(OTHER_KEY_HEX)


def test_windows_skips_mode_bits_that_mean_nothing_there(
    no_key: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path
) -> None:
    """NTFS reports only a read-only flag in st_mode; protection is the ACL set at creation."""
    monkeypatch.setattr(keys, "ON_WINDOWS", True)
    key_file = write_key(tmp_path / "k", OTHER_KEY_HEX)
    key_file.chmod(0o644)
    monkeypatch.setenv(config.KEY_FILE_ENV, str(key_file))
    assert keys.load_key(repo) == bytes.fromhex(OTHER_KEY_HEX)


def test_windows_keeps_every_other_key_check(
    no_key: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path
) -> None:
    monkeypatch.setattr(keys, "ON_WINDOWS", True)
    monkeypatch.setenv(config.KEY_FILE_ENV, str(write_key(repo / "k", OTHER_KEY_HEX)))
    with pytest.raises(KeyProblem, match="inside the repository"):
        keys.load_key(repo)
    monkeypatch.setenv(config.KEY_FILE_ENV, str(write_key(tmp_path / "short", "ab" * 31)))
    with pytest.raises(KeyProblem, match="shorter"):
        keys.load_key(repo)


# ---- creating a key (make key, enron-case key, the one command) -----------------------------


@POSIX_ONLY
def test_new_key_is_random_hex_owner_only_and_loads(
    no_key: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path
) -> None:
    target = tmp_path / "home" / ".config" / "enron-case" / "key"
    assert keys.create_key_file(target, repo)
    assert stat.S_IMODE(target.stat().st_mode) == config.KEY_FILE_MODE
    assert stat.S_IMODE(target.parent.stat().st_mode) == config.KEY_DIR_MODE
    text = target.read_bytes()
    assert text.endswith(b"\n")
    assert len(bytes.fromhex(text.decode("ascii"))) == config.MIN_KEY_BYTES
    monkeypatch.setenv(config.KEY_FILE_ENV, str(target))
    assert keys.load_key(repo) == bytes.fromhex(text.decode("ascii"))


def test_two_new_keys_differ(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path) -> None:
    monkeypatch.setattr(keys, "ON_WINDOWS", False)
    first, second = tmp_path / "a", tmp_path / "b"
    keys.create_key_file(first, repo)
    keys.create_key_file(second, repo)
    assert first.read_bytes() != second.read_bytes()


def test_existing_key_file_is_left_untouched(tmp_path: Path, repo: Path) -> None:
    target = write_key(tmp_path / "key", OTHER_KEY_HEX)
    assert not keys.create_key_file(target, repo)
    assert target.read_text(encoding="utf-8") == OTHER_KEY_HEX + "\n"


def test_new_key_inside_the_repository_is_refused(repo: Path) -> None:
    target = repo / "secrets" / "key"
    with pytest.raises(KeyProblem) as info:
        keys.create_key_file(target, repo)
    assert info.value.exit_code == 3
    assert not target.exists()
    assert not target.parent.exists()


Run = list[list[str]]


def fake_icacls(monkeypatch: pytest.MonkeyPatch, returncode: int) -> Run:
    """Pretend to be Windows with icacls; record each command instead of running it."""
    calls: Run = []

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, returncode, "", "")

    monkeypatch.setattr(keys, "ON_WINDOWS", True)
    monkeypatch.setattr(
        "enron_case.pseudo.keys.shutil.which", lambda name: rf"C:\Windows\System32\{name}.exe"
    )
    monkeypatch.setattr("enron_case.pseudo.keys.subprocess.run", run)
    monkeypatch.setattr("enron_case.pseudo.keys.getpass.getuser", lambda: "analyst")
    monkeypatch.setenv("USERDOMAIN", "WORKSTATION")
    return calls


def test_new_key_on_windows_gets_an_owner_only_acl(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path
) -> None:
    calls = fake_icacls(monkeypatch, returncode=0)
    target = tmp_path / "key"
    assert keys.create_key_file(target, repo)
    assert calls == [
        [
            r"C:\Windows\System32\icacls.exe",
            str(target),
            "/inheritance:r",
            "/grant:r",
            r"WORKSTATION\analyst:F",
        ]
    ]
    assert len(bytes.fromhex(target.read_text(encoding="ascii"))) == config.MIN_KEY_BYTES


def test_key_whose_acl_cannot_be_set_is_removed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path
) -> None:
    fake_icacls(monkeypatch, returncode=5)
    target = tmp_path / "key"
    with pytest.raises(KeyProblem, match="owner") as info:
        keys.create_key_file(target, repo)
    assert info.value.exit_code == 3
    assert not target.exists()


def test_key_without_icacls_is_removed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repo: Path
) -> None:
    fake_icacls(monkeypatch, returncode=0)
    monkeypatch.setattr("enron_case.pseudo.keys.shutil.which", lambda name: None)
    target = tmp_path / "key"
    with pytest.raises(KeyProblem):
        keys.create_key_file(target, repo)
    assert not target.exists()
