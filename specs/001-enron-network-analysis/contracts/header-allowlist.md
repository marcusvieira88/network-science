# Contract: Header Allowlist (v1)

The deliberate line asked for by the brief: which header fields are content, which are direct
identifiers, and which are usable metadata. This is the single source for `ingest/allowlist.py`
and for the contract test that compares the two.

**Rule**: a field not listed as *usable* or *identifier, ingest only* is dropped by the parser.
For dropped fields the value is never assigned to a variable that outlives the line being read.
Unknown field names are counted by name; their values are discarded.

The field list is the set expected in this corpus; S1 reports every field name it actually
encounters, and any new name defaults to **dropped** until ruled on here.

| Header field | Ruling | Reaches | Why |
|--------------|--------|---------|-----|
| `Date` | usable metadata | restricted (hour), release (week) | When. Normalized to UTC; truncated because second-level timestamps fingerprint individuals |
| `From` | direct identifier | ingest only → pseudonym | Who sent |
| `To` | direct identifier | ingest only → pseudonym | Who received; role kept as `to` |
| `Cc` | direct identifier | ingest only → pseudonym | Role kept as `cc` |
| `Bcc` | direct identifier | ingest only → pseudonym | Role kept as `bcc`; deduplicated against `Cc` |
| `X-From` | direct identifier (display name) | ingest only, then discarded | Needed to link alias addresses of one sender |
| `X-To`, `X-cc`, `X-bcc` | direct identifier (display names, legacy directory forms) | ingest only, then discarded | Needed to map legacy forms to addresses |
| `X-Origin` | direct identifier (mailbox owner) | ingest only → boolean `is_custodian` | Tells which entities were observed from both sides |
| archive path (owner / folder / file) | identifier + content-like | ingest only → `is_custodian`, `folder_class` | Not a header, but carries the same information as `X-Origin` and `X-Folder` |
| `X-Folder` | **content-like** + identifier | reduced in the parser to `folder_class` ∈ {sent, inbox, deleted, other} by a fixed vocabulary; raw value dropped | Folder names are topic labels chosen by the owner and embed the owner's name |
| `Subject` | **content** | nowhere | A one-line summary of the body |
| `Message-ID` | technical | ingest only (dedupe diagnostics), then discarded | Expected to be assigned at collection per stored file (see research R3, to be verified) |
| `X-FileName` | direct identifier | nowhere | Owner's mailbox file name; no analytical use |
| `Mime-Version`, `Content-Type`, `Content-Transfer-Encoding` | describes content | nowhere | No analytical use; describes the part we do not read |
| anything else | unknown | nowhere (name counted) | Default deny |

## Derived fields allowed past the boundary

| Field | Derived from | Why it is safe enough |
|-------|--------------|-----------------------|
| `pid`, `org_pid` | resolved entity / registered domain, keyed HMAC | not reversible or confirmable without the key |
| `ts_hour` | `Date` | coarsened |
| `role` | which field the recipient was in | no identity |
| `n_recipients` | recipient count | no identity; note it contributes to fingerprinting, which the risk test measures |
| `is_internal` (per entity) | registered domain equals the customer's | the customer is known; individuals are not |
| `entity_type` | address pattern and behaviour | category only |
| `is_custodian` | mailbox ownership | 150 of N; contributes to re-identification risk and is therefore never published per person |

## Tests bound to this contract

- **Allowlist equality**: the set of field names the parser retains equals the *usable* and
  *identifier, ingest only* rows above.
- **Canary**: synthetic messages carry unique markers in body, `Subject`, `X-Folder`, `X-FileName`
  and display names; after a full run, none appears in `data/restricted`, `release/`, the run
  manifest or captured logs, and body/subject markers appear nowhere at all, including
  `data/ingest`.
- **Reader bound**: the header reader, given a stream, consumes no bytes of a message past its
  first blank line other than by skipping to the next member.
