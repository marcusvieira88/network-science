# WP-A Ingest: fetch and parse headers only

**Tasks**: T019–T025. **Owns**: `src/enron_case/ingest/`, `tests/unit/ingest/`.
**Stage functions** in `ingest/stage.py`: `fetch(ctx)` and `parse(ctx)`.
**Reads**: the archive (`ctx.archive`). **Writes**: `header_records`, counts `ingest_counts`.

This package is the only code that ever opens a message. Principle I lives or dies here.

## fetch

- Download `config.CORPUS_URL` to `ctx.path(Zone.RAW, config.CORPUS_ARCHIVE, "w")` if the file
  is missing, resuming a partial download. Verify SHA-256 against `config.CORPUS_SHA256`; raise
  `CorpusError` on mismatch or failure. Tests must not touch the network: inject the downloader.
- The sample run skips `fetch`; the synthetic archive already exists.

## parse

- Stream the tar (`tarfile.open(path, "r|gz")`). For each regular-file member, read lines until
  the first empty line, then stop reading that member. Never call `.read()` on a member, never
  extract, never use `email.parser` on a whole message.
- Decode bytes as Latin-1. Unfold continuation lines: a line starting with space or tab
  continues the previous header; drop the line break and collapse the leading whitespace run to
  one space. Set parse flag `folded` when a retained header was folded.
- Member path `maildir/<owner>/<folder>/.../<n>.`: `mailbox_owner` = `<owner>`;
  `folder_class` = `vocab.folder_class(<folder>)` (the raw folder name is dropped immediately).
  Skip members not under `maildir/<owner>/<folder>/`.
- Allowlist (single source in `ingest/allowlist.py`, matching
  `specs/.../contracts/header-allowlist.md`): keep `Date`, `From`, `To`, `Cc`, `Bcc`, `X-From`,
  `X-To`, `X-cc`, `X-bcc`, `Message-ID`. Drop every other value at once: `Subject`, `X-Folder`,
  `X-FileName`, `X-Origin` (the path gives the owner), MIME fields, unknown fields. Count every
  field *name* seen; never keep a dropped value in a variable that outlives its line.
- `Date`: `email.utils.parsedate_to_datetime`, converted to UTC; unparseable → `ts_utc` null,
  `date_raw_ok` false, flag `bad_date`. Do not range-check here (clean does).
- Address fields: split on `,`, strip, drop empties; keep raw strings (normalisation is
  WP-B's job). Empty `X-*` values → null.
- `file_id` = `vocab.file_id(member_path)`.
- `ingest_counts` (shape `contracts.counts.IngestCounts`): include `header_rulings` mapping
  every seen field name to `usable`, `identifier`, `content`, `technical` or `dropped`, per the
  allowlist contract; unknown names → `dropped`.
- Real corpus: about 517k members. Build rows in batches; aim for well under 10 minutes.

## Acceptance

- On the synthetic archive, `parse` output equals `synth.table("header_records")` exactly
  (compare `manifest.fingerprint`). This is your main test.
- Reader-bound test: a stream whose body is huge or contains a marker is never read past the
  header end (count bytes consumed).
- `Subject`, `X-FileName`, `X-Folder` values and body text appear nowhere in your output.
- Property test (hypothesis) over random header/body splits and folding.
