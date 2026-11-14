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

The network view draws the groups with Sigma.js (WebGL) through React Sigma and graphology, loaded
as a separate chunk only when the view opens; without WebGL, or if the WebGL view fails, it shows
the SVG network. Positions come from one ForceAtlas2 run over the ties of all weeks (fixed
settings and iteration count, no randomness), so groups stay put while the week changes. Each
group is a disc whose area follows group size; each tie a line whose width follows the week's
weight, on one scale for all weeks. Sizes are in layout units (`itemSizesReference: "positions"`)
so everything zooms together. Controls: zoom in, out and reset, fullscreen, search by group label,
and hover highlighting of a group and its ties; a legend shows the size and width scales. Colours
are read from the CSS variables in `src/index.css` and converted to hex (`src/lib/color.ts`).
The "Individuals (anonymous)" mode fills each published group with `n_persons` points at seeded
random positions (seed: the run seed): they have no label, tooltip, hover text or ties, and their
Sigma keys are opaque sequence numbers (`point:<group index>-<index>`). The data mapping is in
`src/lib/sigmaNetwork.ts` and `src/lib/cells.ts`; tests replace React Sigma with
`src/test/reactSigma.tsx`, since jsdom has no WebGL.

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
