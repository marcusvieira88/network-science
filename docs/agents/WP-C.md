# WP-C Identity: resolve addresses to entities

**Tasks**: T032–T037. **Owns**: `src/enron_case/identity/`, `tests/unit/identity/`.
**Stage function**: `identity/stage.py: run(ctx)`.
**Reads**: `messages`, `header_records` (display names, owners). **Writes**: `entities`,
`address_map`, counts `identity_counts`.

## Rules (research R4)

Union-find over normalised addresses from `messages` (senders and recipients), merges in order,
each tagged with its rule and support:

| Rule | Merge when |
|------|-----------|
| N2 | same local part, domains share the same registered domain (last two labels), e.g. `x@ect.org.com` and `x@org.com` |
| N3 | two addresses used as `From` with the same normalised `X-From` display name, each at least `config.name_link_support` times, and local parts compatible (one is `first.last`, the other `flast` or `first_last` / `firstlast` style built from the same tokens) |
| N4 | a legacy directory string in `X-To`/`X-cc` (contains `/` and no `@`, e.g. `John Smith/HOU/ECT@ECT` style without the address) consistently paired at the same list position with one address, ≥ `name_link_support` times; record in `address_map` only if it adds a merge |
| N5 | owner flag: for each mailbox owner, the dominant sender address of its `sent` copies (`messages.sent_copy_owner`) marks that entity `is_custodian`; no merge |

Guards (count blocked merges by guard in `identity_counts.blocked_by_guard`): never merge on a
name alone; never merge across different registered domains; never use generic local parts
(`info`, `admin`, `support`, `news`, `team`, `office`, …) in N2/N3.

- `entity_id` = lexicographically smallest normalised address in the cluster.
- `address_map.rule` is null for the canonical address; otherwise the rule that attached it.
- Types (`classify.py`): `person` by default; `list`, `system`, `role` by documented local-part
  patterns (`mailer-daemon`, `postmaster`, `no.address`, `announcements`, `all.*`, `*.desk`, …)
  and behaviour (never sends and is addressed by many distinct senders → `list`; sends to more
  than `recipient_cap` recipients more than once → `role`). Document each rule in the module.
- `org_domain` = registered domain; `is_internal` = `org_domain == config.internal_domain`.
- When `ctx.has_truth()`, compute pairwise precision/recall of "same entity" against
  `truth["address_to_truth"]`. `evaluate.py` also provides a sampler that draws N merges for
  manual review and records only counts (`manual_checked`, `manual_correct`).

## Acceptance

- Precision ≥ 0.95 on the synthetic truth; the homonym (same name, different organisation)
  stays separate.
- Output equals `synth.table("entities")` and `synth.table("address_map")`, or each difference
  is explained in your report (the fixture types non-persons from ground truth; say where your
  heuristics disagree).
- Result independent of input order (property test).
