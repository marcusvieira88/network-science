# WP-G Risk: attack our own output

**Tasks**: T063–T069. **Owns**: `src/enron_case/risk/`, `tests/unit/risk/`.
**Stage function**: `risk/stage.py: run(ctx)`.
**Reads**: `events`, `entities_p`, `hypothesis_results`, `metric_series`. **Writes**:
`risk_results`.

## Separation (tested by `tests/privacy/test_zones.py`)

- `risk/aux_public.py` is the attacker's own parser of the raw archive (`ctx.archive`): headers
  `From`, `To`, `Cc`, `Date` only, no identity resolution, **no import from `ingest`**, reading
  each member only up to the blank line like the real parser. It is the *only* risk module that
  references the archive or `Zone.RAW`.
- `risk/score.py` is the *only* risk module that touches `Zone.INGEST`, `Zone.TRUTH` or
  `address_map`. It maps attacker guesses (pid → address) to correct/incorrect using
  `address_map` and `pseudo.pseudonymize.person_pid(load_key(), entity_id)` (WP-D interface),
  and returns counts and rates only.
- Attack code gets only a release variant and auxiliary features. It never sees truth.

## Attacks (research R12)

- A1 outsider: per-address features from the public archive (weekly sent counts, weekly
  received counts, degree, first/last active week). Match to per-pid features of the release
  by nearest neighbour on the weekly activity vector; guess = best match.
- A2 insider (stretch): a few known seed identities (take 3 custodians as seeds from the
  scorer's side, passed in as pid → address) and propagate through the release graph by
  neighbour-signature matching.
- Uniqueness: share of persons unique on attacker-observable features; anonymity-set sizes.

## Release variants (WP-H interface)

`enron_case.release.variants.build_r0(events, entities_p) -> pl.DataFrame` (node-level weekly
edges, restricted zone, in memory), `build_r1(...)` and `build_r2(...)` (aggregate tables).
Until WP-H merges, inject builders in tests.

## Utility

For each variant recompute the headline effect (`finding.stats.effect_size`, WP-F interface)
from the data that variant exposes; `utility_effect_ratio` = variant effect / restricted
effect; `finding_survives` = same sign and interval excluding 0 where computable.

## Acceptance

- On synthetic data where truth is known, the reported re-identification rate equals the rate
  computed directly from ground truth.
- Against R0, A1 re-identifies most active custodians on the synthetic corpus; against R1 it
  has nothing at person level to match and reports 0 with a stated reason.
- Signature test: attack functions accept no truth or address_map argument.
