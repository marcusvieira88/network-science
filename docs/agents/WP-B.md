# WP-B Clean: normalise, deduplicate, flag noise

**Tasks**: T026–T031. **Owns**: `src/enron_case/clean/`, `tests/unit/clean/`.
**Stage function**: `clean/stage.py: run(ctx)`.
**Reads**: `header_records`. **Writes**: `messages`, counts `clean_counts`.

## Rules

- Address normalisation (rule N1, single source `clean/addresses.py`): lower-case; strip
  whitespace, surrounding quotes and angle brackets, a leading `mailto:`, leading/trailing dots.
  Valid if it then matches `local@domain.tld`. Invalid strings are dropped from the recipient
  list and the message gets flag `bad_address`.
- Recipients: unique per message; an address in several fields keeps the strongest role
  (`vocab.ROLE_STRENGTH`: to > cc > bcc). Sort by address.
- Dedupe (research R3), deterministic:
  1. exact key `vocab.msg_key(sender, ts_utc, recipient addresses)` → merge, rule `exact`;
  2. subset: same sender and same second, one recipient set contains the other → merge into
     the union, rule `subset`.
  A message seen once has rule `none`. `n_copies` = files merged. `owner_copies` = sorted
  owners holding a copy. `sent_copy_owner` = owner of a copy whose `folder_class` is `sent`,
  else null. After merging, recompute `msg_key` from the merged recipients.
- Flags: `date_out_of_range` (outside `config.plausible_start..plausible_end`, kept in counts),
  `no_recipients`, `self_only` (recipients == [sender]), `mass_mailing`
  (`n_recipients > config.recipient_cap`), `bad_address`. Records with null `ts_utc` stay as
  messages (key uses an empty timestamp); they are not deduped by the subset rule.
- `clean_counts` (shape `contracts.counts.CleanCounts`): include the research R3 diagnostic
  `message_id_shared_share` = share of exact-duplicate groups whose copies share one
  Message-ID. When `ctx.has_truth()`, compute pairwise precision/recall of "same message"
  against `truth["file_to_message"]` (keys are member paths; map with `vocab.file_id`).
  Otherwise null.

## Acceptance

- On `synth.table("header_records")`, output equals `synth.table("messages")`; if any row
  differs, find out whether the fixture or your rule is wrong and say which in your report.
- Dedupe precision ≥ 0.95 against truth; recall reported.
- Property tests: dedupe is idempotent and independent of input order.
