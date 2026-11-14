# AI workflow log

Running record of what was delegated to agents, what came back, what was rejected and why, and
how it was verified. The AI-workflow note (`docs/ai-workflow.md`) is distilled from this log.

| Time (T+) | WP | Delegated / done | Result | Rejected or changed, and why | Verified how |
|-----------|----|------------------|--------|------------------------------|--------------|
| 0:00 | Lead | Spec, plan, research, contracts, tasks with Spec Kit | Planning artifacts committed | Scope cut to a 12-hour budget; explorer UI marked stretch | Spec quality checklist |
| 0:00 | Lead | WP0 foundation: config, zones, StageContext, contracts in code, synthetic corpus with ground truth and fixtures for every table, CLI, privacy tests | Gate green (lint, mypy strict, 58 tests) | Sensitivity variant `dedupe=exact` dropped: needs a second clean pass, does not fit 12 h. Header rulings travel in `ingest_counts` so release never imports ingest. `data_quality` gained an `order` column as sort key | `make gate`; fixtures validate against every contract |
