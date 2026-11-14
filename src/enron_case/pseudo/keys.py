"""Master key resolution, labelled subkeys and the key fingerprint (contracts/cli.md, R5).

The key and its hex text never appear in an error message, a log line or an output.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

from enron_case.cli import REPO_ROOT
from enron_case.config import (
    DEFAULT_KEY_PATH,
    KEY_ENV,
    KEY_FILE_ENV,
    MIN_KEY_BYTES,
    SAMPLE_KEY_HEX,
)
from enron_case.errors import KeyProblem

PERSON_LABEL = "person-v1"
ORG_LABEL = "org-v1"
EVENT_LABEL = "event-v1"
SUBKEY_LABELS = (PERSON_LABEL, ORG_LABEL, EVENT_LABEL)

FINGERPRINT_MESSAGE = b"fingerprint-v1"
FINGERPRINT_HEX_CHARS = 8


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
    return _parse_key(resolved.read_text(encoding="ascii", errors="replace"), source)


def _parse_key(hex_text: str, source: str) -> bytes:
    try:
        key = bytes.fromhex(hex_text.strip())
    except ValueError:
        raise KeyProblem(f"key from {source} is not hex text") from None
    if len(key) < MIN_KEY_BYTES:
        raise KeyProblem(f"key from {source} is shorter than {MIN_KEY_BYTES} bytes")
    return key
