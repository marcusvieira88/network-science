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
PERSON = "person"
ENTITY_TYPES = (PERSON, "list", "system", "role", "unknown")
UNASSIGNED_COMMUNITY = -1  # `communities.community` of a person in no baseline community
DEDUPE_RULES = ("none", "exact", "subset")
IDENTITY_RULES = ("N1", "N2", "N3", "N4")
MESSAGE_FLAGS = ("date_out_of_range", "no_recipients", "self_only", "mass_mailing", "bad_address")
# Message flags that take a message out of the network (data-contracts.md, events.in_network);
# `bad_address` is flagged but stays in.
NETWORK_EXCLUSION_FLAGS = ("date_out_of_range", "no_recipients", "self_only", "mass_mailing")
PARSE_FLAGS = ("no_header_end", "bad_date", "folded", "decode_error")
CORE_SCOPE = "core"
OBSERVED_SCOPE = "observed"
SCOPES = (CORE_SCOPE, OBSERVED_SCOPE)
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
NAIVE_RELEASE = "R0"  # the person-level baseline every mitigation is measured against
RELEASE_VARIANTS = (NAIVE_RELEASE, "R1", "R2")
# A1 outsider; A2 insider who knows a few custodians; A3 the same propagation seeded with every
# custodian, because the mailbox folder names of the public corpus name them all.
ATTACKERS = ("A1", "A2", "A3")

PSEUDONYM_LEN = 16
PERSON_PREFIX = "p_"
ORG_PREFIX = "o_"
EVENT_PREFIX = "e_"
MESSAGE_PREFIX = "m_"
# Lower-case base32 alphabet, as `pseudonym` renders a digest.
_PSEUDONYM_BODY = f"[a-z2-7]{{{PSEUDONYM_LEN}}}"
PSEUDONYM_PATTERN = f"^{PERSON_PREFIX}{_PSEUDONYM_BODY}$"
ORG_PSEUDONYM_PATTERN = f"^{ORG_PREFIX}{_PSEUDONYM_BODY}$"
EVENT_ID_PATTERN = f"^{EVENT_PREFIX}{_PSEUDONYM_BODY}$"
MESSAGE_PSEUDONYM_PATTERN = f"^{MESSAGE_PREFIX}{_PSEUDONYM_BODY}$"
# Any of these in a restricted or release artifact is an identifier leak.
LEAK_PATTERNS = ("@", PERSON_PREFIX + _PSEUDONYM_BODY, ORG_PREFIX + _PSEUDONYM_BODY)
# One expression matching any of LEAK_PATTERNS.
LEAK_PATTERN = "|".join(f"(?:{pattern})" for pattern in LEAK_PATTERNS)


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
