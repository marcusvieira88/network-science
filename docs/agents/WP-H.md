# WP-H Release: minimum group size and published tables

**Tasks**: T070–T074. **Owns**: `src/enron_case/release/`, `tests/unit/release/`.
**Stage function**: `release/stage.py: run(ctx)`.
**Reads**: restricted tables (`metric_series`, `hypothesis_results`, `risk_results`,
`snapshots`, `communities`, `events`, `entities_p`) and counts (`ingest_counts`,
`clean_counts`, `identity_counts`, `pseudo_counts`). **Writes** (release, CSV):
`data_quality`, `header_fields`, `weekly_metrics`, `hypotheses`, `risk`,
`degree_distribution`, `community_graph`, `community_groups`.

## kanon.py: the single enforcement point

Every release table passes through it before `ctx.write`. Any person count below
`config.k_min` is suppressed (null); a row derived from a suppressed group is dropped or
coarsened; any pid, org pid or `@` raises `PrivacyViolation`. Also guard against differencing:
a published total minus published parts must not reveal a suppressed cell.

## variants.py (public interface used by WP-G)

```python
def build_r0(events: pl.DataFrame, entities_p: pl.DataFrame) -> pl.DataFrame
    # node-level weekly person edges: week, src_pid, dst_pid, weight (never written to release)
def build_r1(...) -> dict[str, pl.DataFrame]   # the aggregate release tables
def build_r2(..., seed: int) -> dict[str, pl.DataFrame]   # R1 + seeded Laplace noise on counts and weights
```

R1 coarsening: weekly resolution, degree buckets (`1`, `2-4`, `5-9`, `10+` per half-year),
per-release re-keyed group labels.

## Tables

- `weekly_metrics`: from `metric_series`; `value` and `n_active` null when `n_active < k`.
- `degree_distribution`: persons per (half-year period, weighted-degree bucket), suppressed < k.
- `community_graph` / `community_groups`: groups are baseline communities with ≥ k persons,
  labelled `G01…` by descending size (no link to pids); smaller communities merged into
  `other`; a (week, src, dst) tie with fewer than k distinct senders is dropped.
- `data_quality` (rows ordered by `order`) and `header_fields` from the counts files
  (`ingest_counts.header_rulings` gives the ruling; never import `ingest`).
- `hypotheses` = `hypothesis_results`; `risk` = `risk_results`.

## Acceptance

- Property test: random tables never leave `kanon` with a person count < k.
- Built from fixtures, every table equals or is consistent with the release fixtures in
  `synth.fixtures`; nothing written contains a pid or `@`.
