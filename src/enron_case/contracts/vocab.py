"""Contract-level vocabulary and derivations shared by producers, consumers and fixtures.

Everything here is defined by specs/001-enron-network-analysis/contracts/. Import it; never
re-implement it.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterable
from datetime import datetime

FOLDER_CLASSES = ("sent", "inbox", "deleted", "other")

# Fixed vocabulary that reduces a raw folder name to a class. The raw name is never stored.
FOLDER_VOCAB: dict[str, str] = {
    "sent": "sent",
    "sent_items": "sent",
    "_sent_mail": "sent",
    "inbox": "inbox",
    "deleted_items": "deleted",
}

# Header field names ruled on in contracts/header-allowlist.md. Only these names are published
# in release/header_fields.csv; any other name is counted under OTHER_HEADER_FIELD.
KNOWN_HEADER_FIELDS = (
    "Message-ID",
    "Date",
    "From",
    "To",
    "Cc",
    "Bcc",
    "Subject",
    "Mime-Version",
    "Content-Type",
    "Content-Transfer-Encoding",
    "X-From",
    "X-To",
    "X-cc",
    "X-bcc",
    "X-Folder",
    "X-Origin",
    "X-FileName",
)
OTHER_HEADER_FIELD = "(other)"

RECIPIENT_ROLES = ("to", "cc", "bcc")
ROLE_STRENGTH = {"to": 3, "cc": 2, "bcc": 1}
ENTITY_TYPES = ("person", "list", "system", "role", "unknown")
DEDUPE_RULES = ("none", "exact", "subset")
IDENTITY_RULES = ("N1", "N2", "N3", "N4")
MESSAGE_FLAGS = ("date_out_of_range", "no_recipients", "self_only", "mass_mailing", "bad_address")
PARSE_FLAGS = ("no_header_end", "bad_date", "folded", "decode_error")
SCOPES = ("core", "observed")
# metric_series label of the main analysis; every other label is a sensitivity variant.
DEFAULT_VARIANT = "default"
METRICS = (
    "volume",
    "active_persons",
    "density",
    "reciprocity",
    "indegree_gini",
    "cross_community_share",
    "external_share",
    "tie_turnover",
)
HYPOTHESES = ("H1", "H2", "H3", "H4")
SUPPORT = ("yes", "no", "inconclusive")
CONFIDENCE = ("high", "moderate", "low")
RELEASE_VARIANTS = ("R0", "R1", "R2")
ATTACKERS = ("A1", "A2")

PSEUDONYM_LEN = 16
PERSON_PREFIX = "p_"
ORG_PREFIX = "o_"
EVENT_PREFIX = "e_"
MESSAGE_PREFIX = "m_"
PSEUDONYM_PATTERN = r"^p_[a-z2-7]{16}$"
ORG_PSEUDONYM_PATTERN = r"^o_[a-z2-7]{16}$"
# Any of these in a restricted or release artifact is an identifier leak.
LEAK_PATTERNS = (r"@", r"p_[a-z2-7]{16}", r"o_[a-z2-7]{16}")


def folder_class(raw_folder: str) -> str:
    """Reduce a raw folder name to its class without retaining the name."""
    return FOLDER_VOCAB.get(raw_folder.strip().lower(), "other")


def file_id(member_path: str) -> str:
    """Stable id of one archive member: first 16 hex chars of SHA-256 of its path."""
    return hashlib.sha256(member_path.encode("utf-8")).hexdigest()[:16]


def msg_key(sender: str | None, ts_utc: datetime | None, recipients: Iterable[str]) -> str:
    """Message key: SHA-256 over sender, timestamp to the second, sorted recipients."""
    stamp = ts_utc.strftime("%Y-%m-%dT%H:%M:%S") if ts_utc is not None else ""
    parts = [sender or "", stamp, *sorted(set(recipients))]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]


def format_pseudonym(prefix: str, digest: bytes) -> str:
    """Render an HMAC digest as `<prefix><16 lowercase base32 chars>`."""
    encoded = base64.b32encode(digest).decode("ascii").lower().rstrip("=")
    return prefix + encoded[:PSEUDONYM_LEN]
