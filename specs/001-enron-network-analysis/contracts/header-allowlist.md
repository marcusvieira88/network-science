# Contract: Header Allowlist (v1, as enforced)

The deliberate line asked for by the brief: which header fields are content, which are direct
identifiers, and which are usable metadata. This is the single source for `ingest/allowlist.py`
(`RULINGS`, `RETAINED`) and for the contract test `tests/unit/ingest/test_allowlist.py`, which
parses the table below and compares it with the code.

**The promise, stated precisely**: content is never decoded, parsed, held, stored or logged.
`Subject` lines are discarded as the header is scanned; body bytes pass through the decompressor
and are skipped; a folder name is reduced at once to one of four classes and never kept.

**Rule**: a field not listed as *usable* or reaching *ingest only* is dropped by the parser. For
dropped fields the value is never assigned to a variable that outlives the line being read.
Every field name in the table below is counted by name (`ingest_counts.header_fields`); every
other name is counted under `(other)` without its spelling, because an unknown "field name" can be
a fragment of message text. Values of unknown fields are discarded and their ruling defaults to
**dropped**.

## How the reader enforces it

`ingest/headers.py` is the only code that touches the bytes of a message. For each archive
member it reads line by line and:

1. **stops at the first blank or whitespace-only line** (the end of the header block) and never
   reads further;
2. **stops at the first line that is neither a continuation line nor a valid `Name: value`
   header line** (an RFC 5322 field name: printable ASCII without colon or whitespace);
3. **stops after `MAX_HEADER_LINES` physical lines or `config.MAX_HEADER_BYTES` bytes**, caps
   far above the longest real header (a line cut short by the byte cap ends the block);
4. classifies each line by field name as soon as it is read; the value of a field that is not
   kept is discarded with that line.

In cases 2 and 3, and at end of stream without a blank line, the block is marked *not ended* and
`ingest/parse.py` **rejects the whole member** (`rejected.no_header_end` in `ingest_counts`), so
body text can never be taken for header fields or for recipients. A member outside the
`maildir/<owner>/<folder>/…` layout is rejected as `outside_maildir`. Field names are counted only
for members that are parsed.

**Publishing field names**: `release/header_fields.csv` lists only the field names in
`contracts/vocab.KNOWN_HEADER_FIELDS` (the rows of the table below) and the row `(other)` with
ruling `dropped`, which the parser already counts without the unknown names' spelling.

## Rulings

| Header field | Ruling | Reaches | Why |
|--------------|--------|---------|-----|
| `Date` | usable metadata | restricted (hour), release (week) | When. Normalized to UTC; truncated to the hour because second-level timestamps fingerprint individuals |
| `From` | direct identifier | ingest only → pseudonym | Who sent |
| `To` | direct identifier | ingest only → pseudonym | Who received; role kept as `to` |
| `Cc` | direct identifier | ingest only → pseudonym | Role kept as `cc` |
| `Bcc` | direct identifier | ingest only → pseudonym | Role kept as `bcc`; a recipient in several fields keeps the strongest role (to > cc > bcc). In this corpus every `Bcc` line repeats the `Cc` line |
| `X-From` | direct identifier (display name) | ingest only, then discarded | Needed to link alias addresses of one sender |
| `X-To`, `X-cc`, `X-bcc` | direct identifier (display names, legacy directory forms) | ingest only, then discarded | Needed to map legacy forms to addresses |
| `Message-ID` | technical | ingest only (dedupe diagnostics), then discarded | Assigned per stored file at collection, so it does not identify a message across mailboxes (research R3) |
| `X-Origin` | direct identifier (mailbox owner) | nowhere; dropped by the parser | The archive path already names the mailbox owner, so this field adds nothing. Ruled *identifier* in `header_fields.csv`, but not retained |
| `X-Folder` | **content-like** + identifier | nowhere; dropped by the parser | Folder names are topic labels chosen by the owner and embed the owner's name. `folder_class` comes from the archive path instead (see below) |
| `Subject` | **content** | nowhere | A one-line summary of the body |
| `X-FileName` | direct identifier | nowhere | Owner's mailbox file name; no analytical use |
| `Mime-Version`, `Content-Type`, `Content-Transfer-Encoding` | dropped (describes content) | nowhere | No analytical use; describes the part we do not read |
| anything else | unknown → dropped | nowhere (counted as `(other)`, spelling not kept) | Default deny |

The archive path `maildir/<owner>/<folder>/…` is not a header. It is read in the ingest zone
only: the owner becomes `mailbox_owner` (and later `is_custodian`), and the top-level folder is
reduced at once to `folder_class` ∈ {sent, inbox, deleted, other} by the fixed vocabulary
`contracts/vocab.FOLDER_VOCAB`; the raw folder name is never stored.

## Derived fields allowed past the boundary

| Field | Derived from | Why it is safe enough |
|-------|--------------|-----------------------|
| `pid`, `org_pid`, `msg_pid`, `event_id` | resolved entity / registered domain / message key, keyed HMAC | not reversible or confirmable without the key; restricted zone only, never published |
| `ts_hour` | `Date` | coarsened |
| `role` | which field the recipient was in | no identity |
| `n_recipients` | recipient count | no identity; it contributes to fingerprinting, which the risk test measures |
| `is_internal` (per entity) | registered domain equals the customer's | the customer is known; individuals are not |
| `entity_type` | address pattern and behaviour | category only |
| `is_custodian` | mailbox ownership (archive path) | a small known set; contributes to re-identification risk and is therefore never published per person |

## Tests bound to this contract

- **Allowlist equality**: the set of field names the parser retains (`allowlist.RETAINED`)
  equals the *usable* rows and the rows reaching *ingest only* above; every name in
  `allowlist.RULINGS` appears in this file.
- **Dropped values**: a parsed record contains no value of `Subject`, `X-Folder`, `X-Origin`,
  `X-FileName`, MIME fields or unknown fields, while their names are counted.
- **Reader bound**: the reader stops at a blank or whitespace-only line, at a non-header line,
  at the line cap and at the byte cap; a member that ends any way but the first is rejected
  (`tests/unit/ingest/`).
- **Canary**: the synthetic corpus carries unique markers in bodies, subjects, folder names and
  file names; after a full run, none of the four appears in any zone, `data/ingest` included,
  or in the logs. Identifiers (`@`, display names, mailbox owners' folder names) appear nowhere
  past the boundary: not in `data/restricted`, `release/`, the UI data, the documents, the run
  manifest or the logs (`tests/privacy/test_canary.py`).
