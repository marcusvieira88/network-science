# WP-J Explorer UI (stretch)

**Tasks**: T089–T098. **Owns**: `src/enron_case/uiexport/`, `tests/unit/uiexport/`, `ui/`.
**Stage function**: `uiexport/stage.py: run(ctx)` (stage `ui-data`).
**Reads**: release tables only. **Writes**: `ui/public/data/release.json`
(`ctx.path(Zone.UI, "release.json", "w")`).

## Export (Python)

Convert the release tables (`data_quality`, `header_fields`, `weekly_metrics`, `hypotheses`,
`risk`, `degree_distribution`, `community_graph`, `community_groups`) plus parameters and
public event dates (`config.PUBLIC_EVENTS`) into one JSON file with a documented shape.
Refuse (raise `PrivacyViolation`) any value matching `vocab.LEAK_PATTERNS` or any person count
below `k_min`. Same input → byte-identical JSON. `uiexport` may import only `zones`, `config`,
`contracts`, `context`, `errors` (tested).

## UI (`ui/`)

- Vite + React 18 + TypeScript strict + Tailwind + shadcn/ui. Dark theme only: near-black
  background, one accent colour, muted borders, bundled font (no Google Fonts, no CDN, no
  analytics). Node 22 is installed; use `npm`.
- Views: Overview (headline finding card + key numbers), Metrics (shadcn chart / Recharts:
  metric, scope and variant selectors, change-point and public-event markers, shaded baseline,
  nulls as gaps), Network (`d3-force` layout computed once and kept stable; nodes = groups sized
  by `n_persons`, edges = weekly weight; week slider with play/pause; a visible note that nodes
  are groups of at least k people), Hypotheses table, Data quality (funnel + header ruling),
  Privacy and risk (R0/R1/R2 by attacker, before/after), Limits.
- Data: `ui/src/lib/data.ts` types and runtime validation; a committed
  `ui/public/data/release.sample.json` generated from the release fixtures so the UI builds and
  tests without a pipeline run (the app loads `release.json` and falls back to the sample with a
  visible "sample data" badge).
- Scripts in `ui/package.json`: `dev`, `build`, `preview`, `lint`, `typecheck`, `test`
  (Vitest + Testing Library). `ui/scripts/check-build.mjs` fails if the build contains an
  external URL. `ui/src/privacy.test.ts` asserts no `@`, no pid pattern and no person count
  below 5 in the loaded data and no per-person rendering.

## Acceptance

- `cd ui && npm ci && npm run lint && npm run typecheck && npm test && npm run build && node scripts/check-build.mjs` green.
- `make gate` green (Python side). Commit `ui/package-lock.json`.
