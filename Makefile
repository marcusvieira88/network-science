.PHONY: all check sample gate key clean fixtures ui ui-sample ui-gate ui-deps
.DEFAULT_GOAL := all

# uv on PATH, else its installers' default folders (a fresh install is not on PATH until a new
# terminal is opened).
UV ?= $(or $(shell command -v uv 2>/dev/null),$(wildcard $(HOME)/.local/bin/uv),$(wildcard $(HOME)/.cargo/bin/uv),uv)
# Every step lives in the `enron-case` CLI (contracts/cli.md), which runs the same on macOS,
# Linux and Windows; these targets only call it. Windows runs the same commands without make:
# `uv run enron-case all` or run.cmd.
CLI := $(UV) run --locked enron-case
# KEY_FILE (where to create a key) and UI_PORT reach the CLI as environment variables; unset,
# they arrive empty and the CLI uses its defaults.
export KEY_FILE UI_PORT
# The CLI cannot report a missing uv, so the two run targets check for it first.
NEED_UV = command -v $(UV) >/dev/null || { \
  echo "==> missing prerequisite: uv (https://docs.astral.sh/uv/)" >&2; \
  echo "    install it:  curl -LsSf https://astral.sh/uv/install.sh | sh   (or: brew install uv)" >&2; \
  echo "    then open a new terminal and run make again" >&2; exit 1; }

## The one command (bare `make` is the same): prerequisites, locked dependencies, key, corpus,
## full pipeline, Python and UI gates, UI build, summary, then serve the explorer until Ctrl+C.
all:
	@$(NEED_UV); $(CLI) all

## Everything `make all` does except serving the explorer (reviewers without a server).
check:
	@$(NEED_UV); $(CLI) check

## Full pipeline on the bundled synthetic corpus.
sample:
	@$(UV) sync --locked
	@$(UV) run enron-case run --sample

## Lint, types and all tests (no corpus needed).
gate:
	@$(UV) sync --locked
	@$(CLI) gate

## Create a key outside the repository if none exists.
key:
	@$(CLI) key

## Write synthetic fixtures for inspection into tests/fixtures (git-ignored).
fixtures:
	@$(UV) run python -m enron_case.synth --out tests/fixtures

clean:
	rm -rf data/ingest data/restricted data/sample data/logs release-sample tests/fixtures

## Install UI dependencies (`npm ci`) only when ui/package-lock.json is newer than them.
ui-deps:
	@$(CLI) ui-deps

## Explorer UI on its own (needs Node 20+): export release/, build, serve.
ui: ui-deps
	@$(CLI) stage ui-data
	@cd ui && npm run build && npm run preview

ui-sample: ui-deps
	@$(CLI) stage ui-data --sample
	@cd ui && npm run build && npm run preview

ui-gate:
	@$(CLI) ui-gate
