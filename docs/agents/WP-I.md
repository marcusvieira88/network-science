# WP-I Report and documents

**Tasks now**: T078–T081, and drafts of T085–T087. **Owns**: `src/enron_case/report/`,
`tests/unit/report/`, `README.md`, `docs/decision-record.md`, `docs/ai-workflow.md`,
`docs/slides.md`. **Stage function**: `report/stage.py: run(ctx)`.
**Reads**: release tables only (and `run_manifest.json` if present). **Writes**:
`release/report.md` (`ctx.path(Zone.RELEASE, "report.md", "w")`) and, on non-sample runs, the
three documents in `Zone.DOCS` with numbers injected.

## Report (`render.py`, `quality.py`)

Sections: what we found in the data (cleaning funnel from `data_quality`, header ruling table
from `header_fields`), the finding (headline from `hypotheses` with effect, interval, p, Holm p,
robustness, confidence in words; or the "no hypothesis supported" text), all four hypotheses,
privacy and risk (`risk` table, before/after), limits (at least three, always present).
Plain Markdown tables. Every number comes from a release table; none is typed.

## Number injection

Documents contain `{{name}}` placeholders (e.g. `{{dedupe_removed}}`, `{{headline_effect}}`,
`{{reid_r0_a1}}`). `render.inject(text, values)` replaces them; an unknown or unfilled
placeholder fails the build. Keep the placeholder→value table in one place.

## Documents (drafts now, final after the lead's judgments)

- `docs/decision-record.md`: one page — architecture (link `docs/architecture.md`), trade-offs
  (strict content line incl. Subject; rule-based identity; HMAC and its limits; aggregates-only
  release), what changes with real customer data (metadata-only connectors, customer-side key
  custody and entity registry, retention, works council review, data residency, formal privacy
  budget). Read `specs/001-enron-network-analysis/research.md` for the reasoning.
- `docs/ai-workflow.md`: skeleton with the structure of the note; the lead fills it from
  `docs/ai-workflow-log.md` at the end.
- `docs/slides.md`: Marp-compatible, at most 12 slides (outline in task T087), with placeholders.
- `README.md`: what this is, prerequisites (Python 3.12, uv, make), `make key` then `make all`,
  `make gate`, `make sample`, reading order, what is and is not committed.

## Acceptance

- Renders from the release fixtures (copy them into a temp release zone).
- Test: every number in the output traces to a release table cell; unfilled placeholder fails;
  limits section present.
