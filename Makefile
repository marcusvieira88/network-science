.PHONY: all sample gate key clean fixtures ui ui-sample ui-gate

UV ?= uv
KEY_FILE ?= $(HOME)/.config/enron-case/key
# Fixed key for the synthetic sample and tests only. Never used for real data.
TEST_KEY := 7465737400000000000000000000000000000000000000000000000000000000

## The one command: fetch, verify, run every stage, run the gate, print the report path.
all:
	@$(UV) sync --locked
	@$(UV) run enron-case check-key || { echo "No key found. Run: make key" >&2; exit 3; }
	@$(UV) run enron-case run
	@ENRON_CASE_KEY=$(TEST_KEY) $(UV) run pytest -q
	@echo release/report.md

## Full pipeline on the bundled synthetic corpus.
sample:
	@$(UV) sync --locked
	@ENRON_CASE_KEY=$(TEST_KEY) $(UV) run enron-case run --sample

## Lint, types and all tests (no corpus needed).
gate:
	@$(UV) sync --locked
	@$(UV) run ruff check src tests
	@$(UV) run ruff format --check src tests
	@$(UV) run mypy
	@ENRON_CASE_KEY=$(TEST_KEY) $(UV) run pytest -q

## Create a key outside the repository if none exists.
key:
	@if [ -f "$(KEY_FILE)" ]; then echo "Key exists at $(KEY_FILE)"; else \
		mkdir -p "$$(dirname "$(KEY_FILE)")" && \
		umask 077 && python3 -c "import secrets; print(secrets.token_hex(32))" > "$(KEY_FILE)" && \
		chmod 600 "$(KEY_FILE)" && echo "Key written to $(KEY_FILE)"; fi

## Write synthetic fixtures for inspection into tests/fixtures (git-ignored).
fixtures:
	@$(UV) run python -m enron_case.synth --out tests/fixtures

clean:
	rm -rf data/ingest data/restricted data/sample release-sample tests/fixtures

## Optional explorer UI (needs Node 20+). Not part of `make all`.
ui:
	@$(UV) run enron-case stage ui-data
	@cd ui && npm ci && npm run build && npm run preview

ui-sample:
	@ENRON_CASE_KEY=$(TEST_KEY) $(UV) run enron-case stage ui-data --sample
	@cd ui && npm ci && npm run build && npm run preview

ui-gate:
	@cd ui && npm ci && npm run lint && npm run typecheck && npm test && node scripts/check-build.mjs
