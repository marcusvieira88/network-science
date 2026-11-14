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

Regenerate the sample after a contract or fixture change:
`UPDATE_UI_SAMPLE=1 uv run pytest tests/unit/uiexport -k committed_ui_sample`.
