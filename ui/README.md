# Explorer UI

A static, dark interface over the published release (research R14). It reads one file,
`public/data/release.json`, written by the `ui-data` stage from `release/` (shape documented in
`src/enron_case/uiexport/export.py`). Without it, the app loads the committed
`public/data/release.sample.json` (an export of the synthetic release fixtures) and shows a
"Sample data" badge.

```bash
make ui-sample          # export the sample release, build and serve locally
make ui                 # same from release/
npm ci && npm run lint && npm run typecheck && npm test && npm run build && node scripts/check-build.mjs
```

Privacy: the data holds only release tables (groups of at least k people, no identifiers);
`src/lib/privacy.ts` refuses data that breaks that, `src/privacy.test.ts` checks the data and every
view, and `scripts/check-build.mjs` fails if the build references another origin. The production
build carries a Content-Security-Policy that blocks requests to any other origin. Fonts are
bundled; nothing is fetched from a CDN.

The network view draws the groups as a 3D force graph (`react-force-graph-3d`, three.js), loaded
as a separate chunk only when the view opens; without WebGL it shows the 2D network. Each group is
a glowing cell (volume follows group size; three's `UnrealBloomPass` adds the glow) and each tie a
curved line with signal particles whose number and speed follow the week's weight. The
"Individuals (anonymous)" mode fills each published group with `n_persons` points at seeded random
positions (seed: the run seed): they carry no id, label, tooltip or data, and ties stay between
groups. The data mapping is in `src/lib/network3d.ts` and `src/lib/cells.ts`; the three.js objects
in `src/components/cellObjects.ts`. `three/webgpu` is aliased to a throwing stub
(`src/vendor/three-webgpu-stub.ts`) because the WebGPU renderer is imported but never used.
`scripts/check-build.mjs` accepts two exact URL literals in that chunk (a shader comment and a
library error message), each only in its own context; see `NON_REQUEST_LITERALS` there.

The hypotheses view shows one list: the `hypotheses` table (stated before any data, with their
artifact checks under each row) and the `exploratory` table (stated before being computed), merged
and ordered by the number in each id (`src/lib/hypotheses.ts`). The headline and every confident
outcome are marked "Held true"; the Overview repeats each held-true measure in one line.

The clusters view is a chord diagram of message weight between the published groups
(`community_groups`, `community_graph`) over the baseline year, the exploratory crisis weeks
(`windows.crisis` in the data, from `config.CRISIS_WINDOW`) or all weeks; a week counts when any of its
days falls inside the period. Data shaping is in `src/lib/clusters.ts`; the drawing uses
`d3-chord` and `d3-shape` (already bundled through Recharts) with plain SVG, in the main chunk.

Regenerate the sample after a contract or fixture change:
`UPDATE_UI_SAMPLE=1 uv run pytest tests/unit/uiexport -k committed_ui_sample`.
