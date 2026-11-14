# AI workflow log

Running record of what was delegated to agents, what came back, what was rejected and why, and
how it was verified. The AI-workflow note (`docs/ai-workflow.md`) is distilled from this log.

| Time (T+) | WP | Delegated / done | Result | Rejected or changed, and why | Verified how |
|-----------|----|------------------|--------|------------------------------|--------------|
| 0:00 | Lead | Spec, plan, research, contracts, tasks with Spec Kit | Planning artifacts committed | Scope cut to a 12-hour budget; explorer UI marked stretch | Spec quality checklist |
| 0:00 | Lead | WP0 foundation: config, zones, StageContext, contracts in code, synthetic corpus with ground truth and fixtures for every table, CLI, privacy tests | Gate green (lint, mypy strict, 58 tests) | Sensitivity variant `dedupe=exact` dropped: needs a second clean pass, does not fit 12 h. Header rulings travel in `ingest_counts` so release never imports ingest. `data_quality` gained an `order` column as sort key | `make gate`; fixtures validate against every contract |
| ~2:30 | WP-A…D, H, I | Six agents in parallel worktrees, each against fixtures | All six gates green; ingest, clean, identity and pseudonymize reproduce their reference fixtures exactly (identity precision and recall 1.0 on synthetic truth) | Agents kept to their briefs and reported every deviation: X-Origin dropped (contract updated), header-field counts in fixture wrong for Cc/Bcc, degree definition ambiguous (set to distinct contacts), templates moved out of `docs/` so a real run cannot overwrite them, per-release salt dropped (release carries no pseudonyms) | Each agent's acceptance tests; merged with no conflicts; `make gate` and `make sample` green through pseudonymize; canary clean |
| ~2:45 | Lead | First real-corpus run, fetch → pseudonymize (T044) | running | — | — |
