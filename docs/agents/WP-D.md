# WP-D Pseudonymize: keys and the boundary

**Tasks**: T038–T042. **Owns**: `src/enron_case/pseudo/`, `tests/unit/pseudo/`.
**Stage function**: `pseudo/stage.py: run(ctx)`.
**Reads** (ingest zone): `messages`, `entities`, `address_map`. **Writes** (restricted):
`events`, `entities_p`, counts `pseudo_counts`.

## keys.py (public interface used by the orchestrator and by WP-G)

```python
def load_key() -> bytes                      # resolution order below; raises KeyProblem
def key_fingerprint(key: bytes) -> str       # HMAC(key, b"fingerprint-v1") hex, first 8 chars
def subkey(key: bytes, label: str) -> bytes  # labels: person-v1, org-v1, event-v1
```

Resolution: `ENRON_CASE_KEY` (64 hex chars) → file at `ENRON_CASE_KEY_FILE` → file at
`~/.config/enron-case/key` (hex text). Raise `KeyProblem` if missing, shorter than 32 bytes, or
if the key file resolves inside the repository. Never log or return the key in an error message.

## pseudonymize.py (public interface used by WP-G's scorer)

```python
def person_pid(key: bytes, entity_id: str) -> str   # vocab.format_pseudonym("p_", HMAC(subkey(person-v1), entity_id))
def org_pid(key: bytes, org_domain: str) -> str     # "o_" with org-v1
```

## Stage

- One `events` row per (message, recipient) for messages with a timestamp and a sender;
  `event_id` = `e_` + HMAC(event-v1, msg_key + "|" + recipient address); `msg_pid` = `m_` +
  HMAC(event-v1, msg_key); `ts_hour` = `ts_utc` truncated to the hour; `weight` =
  1 / `n_recipients`; `in_network` false if the message has any of `date_out_of_range`,
  `no_recipients`, `self_only`, `mass_mailing`.
- Map addresses to entities through `address_map`; types, internal flags and org from
  `entities`. Every entity gets a pid, non-persons included.
- Abort with `PseudonymCollision` if two entities get one pid.
- No mapping table is written anywhere. `pseudo_counts` per `contracts.counts.PseudoCounts`.

## Acceptance

- Same key + same input → identical `events` fingerprint; a different key → disjoint pids and
  identical aggregate counts.
- On the fixture inputs: same number of events, same `in_network` count, same weights as
  `synth.table("events")` (pids differ because the fixture uses its own key).
- No `@` anywhere in your outputs (also enforced by `ctx.write`).
