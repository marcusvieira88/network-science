"""Master key creation and resolution, labelled subkeys and the key fingerprint
(contracts/cli.md, R5).

The key and its hex text never appear in an error message, a log line or an output.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import os
import secrets
import shutil
import subprocess
from pathlib import Path

from enron_case.cli import REPO_ROOT
from enron_case.config import (
    DEFAULT_KEY_PATH,
    KEY_DIR_MODE,
    KEY_ENV,
    KEY_FILE_ENV,
    KEY_FILE_FORBIDDEN_MODE,
    KEY_FILE_MODE,
    MIN_KEY_BYTES,
    ON_WINDOWS,
    SAMPLE_KEY_HEX,
)
from enron_case.errors import KeyProblem

PERSON_LABEL = "person-v1"
ORG_LABEL = "org-v1"
EVENT_LABEL = "event-v1"
SUBKEY_LABELS = (PERSON_LABEL, ORG_LABEL, EVENT_LABEL)

FINGERPRINT_MESSAGE = b"fingerprint-v1"
FINGERPRINT_HEX_CHARS = 8


def create_key_file(path: Path, repo_root: Path = REPO_ROOT) -> bool:
    """Write a new random key to `path`, readable by its owner only, unless a file is already
    there. Returns whether a key was written. A path inside the repository is refused."""
    target = path.expanduser()
    if target.exists():
        return False
    if target.resolve().is_relative_to(repo_root.resolve()):
        raise KeyProblem("refusing to write a key inside the repository")
    target.parent.mkdir(mode=KEY_DIR_MODE, parents=True, exist_ok=True)
    # O_EXCL: never write through a file or link that appeared since the check above.
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, KEY_FILE_MODE)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write((secrets.token_hex(MIN_KEY_BYTES) + "\n").encode("ascii"))
    if ON_WINDOWS:
        _restrict_to_owner(target)
    return True


def _restrict_to_owner(path: Path) -> None:
    """Windows has no mode bits: replace the inherited ACL with one granting the current user
    alone. A key that cannot be restricted is deleted, never left readable."""
    icacls = shutil.which("icacls")
    account = getpass.getuser()
    domain = os.environ.get("USERDOMAIN")
    if domain:
        account = f"{domain}\\{account}"
    if icacls is not None:
        argv = [icacls, str(path), "/inheritance:r", "/grant:r", f"{account}:F"]
        result = subprocess.run(argv, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return
    path.unlink()
    raise KeyProblem("could not restrict the new key file to its owner (icacls); it was removed")


def load_key(repo_root: Path = REPO_ROOT) -> bytes:
    """Resolve the master key: environment, then the named key file, then the default file."""
    from_env = os.environ.get(KEY_ENV)
    if from_env is not None:
        return _parse_key(from_env, KEY_ENV)
    named_file = os.environ.get(KEY_FILE_ENV)
    if named_file is not None:
        return _read_key_file(Path(named_file), KEY_FILE_ENV, repo_root)
    return _read_key_file(Path.home() / DEFAULT_KEY_PATH, "default key file", repo_root)


def load_run_key(sample: bool, repo_root: Path = REPO_ROOT) -> bytes:
    """The key for a run. A real-data run refuses the sample key: it is published in this
    repository, so anyone could recompute the pseudonyms it makes from candidate addresses."""
    key = load_key(repo_root)
    if not sample and key == bytes.fromhex(SAMPLE_KEY_HEX):
        raise KeyProblem("the published sample key cannot pseudonymize real data; run: make key")
    return key


def key_fingerprint(key: bytes) -> str:
    """Comparable between runs, useless for recovering the key."""
    digest = hmac.new(key, FINGERPRINT_MESSAGE, hashlib.sha256).hexdigest()
    return digest[:FINGERPRINT_HEX_CHARS]


def subkey(key: bytes, label: str) -> bytes:
    """Per-purpose key, so pseudonyms made for different purposes cannot be compared."""
    if label not in SUBKEY_LABELS:
        raise KeyProblem(f"unknown subkey label: {label}")
    return hmac.new(key, label.encode("utf-8"), hashlib.sha256).digest()


def keyed_digest(key: bytes, label: str, value: str) -> bytes:
    """HMAC-SHA256 of `value` under the subkey for `label`."""
    return hmac.new(subkey(key, label), value.encode("utf-8"), hashlib.sha256).digest()


def _read_key_file(path: Path, source: str, repo_root: Path) -> bytes:
    resolved = path.expanduser().resolve()
    if resolved.is_relative_to(repo_root.resolve()):
        raise KeyProblem(f"{source} lies inside the repository; move it outside")
    if not resolved.is_file():
        raise KeyProblem(f"no key found ({source} missing); run: make key")
    _check_owner_only(resolved, source)
    return _parse_key(resolved.read_text(encoding="ascii", errors="replace"), source)


def _check_owner_only(path: Path, source: str) -> None:
    """POSIX: refuse any permission bit for group or others. Windows reports no such bits (its
    st_mode reflects only the read-only flag), so there the check is skipped: the key is
    protected by the owner-only ACL that create_key_file sets and by the private user profile
    it lives in (contracts/cli.md)."""
    if ON_WINDOWS:
        return
    if path.stat().st_mode & KEY_FILE_FORBIDDEN_MODE:
        raise KeyProblem(f"{source} is open to group or other users; run: chmod 600 on it")


def _parse_key(hex_text: str, source: str) -> bytes:
    try:
        key = bytes.fromhex(hex_text.strip())
    except ValueError:
        raise KeyProblem(f"key from {source} is not hex text") from None
    if len(key) < MIN_KEY_BYTES:
        raise KeyProblem(f"key from {source} is shorter than {MIN_KEY_BYTES} bytes")
    return key
