.PHONY: all check sample gate key clean fixtures ui ui-sample ui-gate
.DEFAULT_GOAL := all

UV ?= uv
KEY_FILE ?= $(HOME)/.config/enron-case/key
# npm writes this file at the end of `npm ci`; rebuilding it only when the lockfile is newer
# lets every target reuse installed UI dependencies.
UI_DEPS := ui/node_modules/.package-lock.json

## The one command (bare `make` is the same): prerequisites, locked dependencies, key, corpus,
## full pipeline, Python and UI gates, UI build, summary, then serve the explorer until Ctrl+C.
all:
	@KEY_FILE="$(KEY_FILE)" UV="$(UV)" scripts/run-all.sh all

## Everything `make all` does except serving the explorer (CI, reviewers without a server).
check:
	@KEY_FILE="$(KEY_FILE)" UV="$(UV)" scripts/run-all.sh check

## Full pipeline on the bundled synthetic corpus.
sample:
	@$(UV) sync --locked
	@$(UV) run enron-case run --sample

## Lint, types and all tests (no corpus needed).
gate:
	@$(UV) sync --locked
	@$(UV) run ruff check src tests
	@$(UV) run ruff format --check src tests
	@$(UV) run mypy
	@$(UV) run pytest -q

## Create a key outside the repository if none exists.
key:
	@scripts/create-key.sh "$(KEY_FILE)"

## Write synthetic fixtures for inspection into tests/fixtures (git-ignored).
fixtures:
	@$(UV) run python -m enron_case.synth --out tests/fixtures

clean:
	rm -rf data/ingest data/restricted data/sample data/logs release-sample tests/fixtures

$(UI_DEPS): ui/package-lock.json
	@cd ui && npm ci

## Explorer UI on its own (needs Node 20+): export release/, build, serve.
ui: $(UI_DEPS)
	@$(UV) run enron-case stage ui-data
	@cd ui && npm run build && npm run preview

ui-sample: $(UI_DEPS)
	@$(UV) run enron-case stage ui-data --sample
	@cd ui && npm run build && npm run preview

ui-gate: $(UI_DEPS)
	@cd ui && npm run lint && npm run typecheck && npm test && npm run build && node scripts/check-build.mjs
