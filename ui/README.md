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
as a separate chunk only when the view opens; without WebGL it shows the 2D network. The data
mapping is in `src/lib/network3d.ts`. `three/webgpu` is aliased to a throwing stub
(`src/vendor/three-webgpu-stub.ts`) because the WebGPU renderer is imported but never used.
`scripts/check-build.mjs` accepts two exact URL literals in that chunk (a shader comment and a
library error message), each only in its own context; see `NON_REQUEST_LITERALS` there.

Regenerate the sample after a contract or fixture change:
`UPDATE_UI_SAMPLE=1 uv run pytest tests/unit/uiexport -k committed_ui_sample`.
