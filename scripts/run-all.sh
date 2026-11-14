#!/usr/bin/env bash
# The one command (contracts/cli.md): check, install, key, corpus, pipeline, every gate, UI.
#   scripts/run-all.sh        everything, then serve the explorer until Ctrl+C (`make`, `make all`)
#   scripts/run-all.sh check  everything except serving (`make check`)
# Each step prints one line; its full output goes to data/logs/<step>.log and is shown on failure.
# The first failing step stops the run with that step's exit code.
set -euo pipefail

mode=${1:-all}
if [[ $mode != all && $mode != check ]]; then
    echo "usage: $0 [all|check]" >&2
    exit 2
fi

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$repo_root"

UV=${UV:-uv}
MAKE=${MAKE:-make}
KEY_FILE=${KEY_FILE:-$HOME/.config/enron-case/key}
UI_PORT=${UI_PORT:-4173}
MIN_NODE_MAJOR=20
LOG_DIR=data/logs
FAILURE_TAIL_LINES=40

# Run "$@" quietly as one numbered step; on failure show the log's tail and exit with its code.
step() {
    local label=$1 log="$LOG_DIR/$2.log" started=$SECONDS
    shift 2
    printf '==> %-44s' "$label"
    if "$@" >"$log" 2>&1; then
        printf 'ok (%ss)\n' $((SECONDS - started))
    else
        local code=$?
        printf 'FAILED (exit %s)\n' "$code"
        tail -n "$FAILURE_TAIL_LINES" "$log" >&2
        echo "Full log: $LOG_DIR/$(basename "$log")" >&2
        exit "$code"
    fi
}

missing() {
    echo "==> missing prerequisite: $1" >&2
    exit 1
}

# Checked first so a busy port fails in a second, not after the whole run.
port_is_free() {
    node -e "require('net').createServer().once('error', () => process.exit(1))
        .listen($1, '127.0.0.1', function () { this.close(); })"
}

check_prerequisites() {
    command -v "$UV" >/dev/null || missing "uv (https://docs.astral.sh/uv/)"
    "$UV" python find 3.12 >/dev/null 2>&1 || missing "Python 3.12 (uv python install 3.12)"
    command -v node >/dev/null || missing "Node.js >= $MIN_NODE_MAJOR"
    node -e "process.exit(Number(process.versions.node.split('.')[0]) >= $MIN_NODE_MAJOR ? 0 : 1)" ||
        missing "Node.js >= $MIN_NODE_MAJOR (found $(node --version))"
    command -v npm >/dev/null || missing "npm"
    if [[ $mode == all ]] && ! port_is_free "$UI_PORT"; then
        missing "a free port $UI_PORT for the explorer (stop what uses it, or run: UI_PORT=<port> make)"
    fi
    echo "==> prerequisites: uv, Python 3.12, Node $(node --version), npm"
}

# Runs inside `step`'s `if`, where `set -e` is off: chain with && so a failure stops it.
install_dependencies() {
    "$UV" sync --locked && "$MAKE" --no-print-directory ui/node_modules/.package-lock.json
}

# Create a key outside the repository only when none is configured at all; a configured but
# unusable key (ENRON_CASE_KEY or ENRON_CASE_KEY_FILE) stops the run with exit code 3.
ensure_key() {
    if [[ -z ${ENRON_CASE_KEY:-} && -z ${ENRON_CASE_KEY_FILE:-} ]]; then
        if [[ ! -e $KEY_FILE ]]; then
            scripts/create-key.sh "$KEY_FILE" >/dev/null
            echo "==> key: none configured; created a new key at $KEY_FILE (mode 600)"
        fi
        export ENRON_CASE_KEY_FILE=$KEY_FILE # so every stage reads the key just checked
    fi
    "$UV" run --locked enron-case check-key
    echo "==> key: usable key found (never printed)"
}

serve_explorer() {
    cd ui
    exec npm run preview -- --port "$UI_PORT" --strictPort
}

mkdir -p "$LOG_DIR"
check_prerequisites
step "install locked dependencies (uv, npm)" install install_dependencies
ensure_key
step "download and verify the corpus" fetch "$UV" run --locked enron-case stage fetch
step "run the pipeline on the real corpus" pipeline "$UV" run --locked enron-case run
step "Python gate (lint, types, tests, canary)" gate "$MAKE" --no-print-directory gate
step "UI gate (lint, types, tests, build check)" ui-gate "$MAKE" --no-print-directory ui-gate
step "export UI data from release/" ui-data "$UV" run --locked enron-case stage ui-data
step "build the explorer" ui-build npm --prefix ui run build

echo
echo "All steps passed: pipeline, Python gate and UI gate are green."
echo "  Report:   release/report.md"
echo "  Results:  $("$UV" run --locked enron-case summary)"
echo "  Logs:     $LOG_DIR/"
if [[ $mode == check ]]; then
    echo "  Explorer: built in ui/dist (run 'make' to serve it at http://localhost:$UI_PORT)"
    exit 0
fi
echo "  Explorer: http://localhost:$UI_PORT  (Ctrl+C to stop)"
serve_explorer
