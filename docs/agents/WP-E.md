# WP-E Network: weekly snapshots and metrics

**Tasks**: T047–T052. **Owns**: `src/enron_case/network/`, `tests/unit/network/`,
`docs/metrics.md`. **Stage function**: `network/stage.py: run(ctx)`.
**Reads**: `events`, `entities_p`. **Writes**: `snapshots`, `communities`, `metric_series`.

Write `docs/metrics.md` first (definition, range, edge behaviour of each metric, and the
confidence rule of research R11), then the tests, then the code.

## Definitions

- Person network: `in_network` events whose sender and recipient are both `person` and both
  internal. Scope `observed` = all of them; scope `core` = both ends `is_custodian`.
- Week = Monday of the ISO week of `ts_hour`. Analysis window `config.analysis_start..end`.
- `snapshots`: per scope, week, (src, dst): summed `weight`, distinct `msg_pid` count.
- `communities`: Louvain (`networkx.community.louvain_communities`, `seed=config.seed`) on the
  undirected weighted observed graph of the baseline period (`config.baseline_start..end`).
  Persons not active in the baseline get community -1.
- Metrics per scope and week: `volume` (messages), `active_persons`, `density`, `reciprocity`,
  `indegree_gini` (Gini of weighted in-degree over active persons), `cross_community_share`
  (share of weight between two different baseline communities, both ≥ 0),
  `external_share` (from events: share of internal-person senders' weight that goes to
  external persons), `tie_turnover` (1 − Jaccard of edge sets of consecutive weeks).
  A metric is null when the week has fewer than `config.k_min` active persons.
- Variants: `default`; `cap=20` (drop events with `n_recipients` > 20); `window=month` is
  stretch, do it last.

## Public interface (WP-F calls it for leave-one-mailbox-out and the null model)

```python
def compute_series(events: pl.DataFrame, entities_p: pl.DataFrame, communities: pl.DataFrame,
                   config: Config, variant: str = "default",
                   exclude_pids: frozenset[str] = frozenset()) -> pl.DataFrame
    # returns rows in the metric_series schema
```

## Acceptance

- Hand-computed toy graphs (empty, complete, star, two cliques) for every metric.
- On `synth.table("events")` (planted change at 2001-08-13 around hub custodians): core and
  observed `indegree_gini` and `cross_community_share` are higher after the change week than
  before; on `synth_nochange` they are not meaningfully different.
- Undefined weeks give null, not zero.
