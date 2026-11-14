"""The one command (contracts/cli.md): `enron-case all` and `enron-case check`, and the gates
they run (`enron-case gate`, `enron-case ui-gate`).

Written in Python rather than shell so that macOS, Linux and Windows run the same steps; `make`
and `run.cmd` only call it. Each step prints one line; its full output goes to
data/logs/<step>.log and is shown on failure. The first failing step stops the run with that
step's exit code.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from enron_case.cli import REPO_ROOT, load_key_fingerprint, summary_line
from enron_case.config import (
    DEFAULT_KEY_PATH,
    DEFAULT_UI_PORT,
    EXPLORER_HOST,
    FAILURE_TAIL_LINES,
    KEY_ENV,
    KEY_FILE_ENV,
    KEY_FILE_TARGET_ENV,
    MAX_PORT,
    MIN_FREE_DISK_BYTES,
    MIN_NODE_MAJOR,
    ON_WINDOWS,
    PYTHON_GATE,
    STEP_LOG_DIR,
    UI_DEPENDENCY_MARKER,
    UI_GATE,
    UI_LOCKFILE,
    UI_PORT_ENV,
    UV_ENV,
)
from enron_case.context import stderr_log
from enron_case.errors import PipelineError, PrerequisiteMissing, StepFailed
from enron_case.pseudo.keys import create_key_file
from enron_case.zones import Paths

ALL, CHECK = "all", "check"
MODES = (ALL, CHECK)
UV_HINT = "uv (https://docs.astral.sh/uv/)"
PORT_PATTERN = re.compile(r"[0-9]{1,5}")
BYTES_PER_GB = 1024**3
SIGNAL_EXIT_BASE = 128  # a shell reports death by signal N as 128 + N
# Children write their output to log files; on Windows Python would encode it in the locale's
# code page and fail on characters outside it. UTF-8 mode makes every OS write the same bytes.
CHILD_ENVIRONMENT = {"PYTHONUTF8": "1"}


@dataclass(frozen=True)
class Command:
    argv: tuple[str, ...]
    cwd: Path


@dataclass(frozen=True)
class Step:
    label: str
    log_name: str
    commands: tuple[Command, ...]


@dataclass(frozen=True)
class Tools:
    """Executables as found on PATH (on Windows `npm` is `npm.cmd`, which shutil.which finds)."""

    uv: str
    node: str
    npm: str
    python: str = sys.executable


# ---- running commands ------------------------------------------------------------------------


def exit_status(returncode: int) -> int:
    """A child's exit code as a shell reports it (subprocess gives -N for death by signal N)."""
    return SIGNAL_EXIT_BASE - returncode if returncode < 0 else returncode


def _run(command: Command, output: BinaryIO | None) -> int:
    completed = subprocess.run(
        command.argv,
        cwd=command.cwd,
        stdout=output,
        stderr=subprocess.STDOUT if output is not None else None,
        env={**os.environ, **CHILD_ENVIRONMENT},
        check=False,
    )
    return exit_status(completed.returncode)


def run_streaming(commands: Sequence[Command]) -> int:
    """Run `commands` in order in this terminal; the first non-zero exit code stops them."""
    for command in commands:
        code = _run(command, None)
        if code:
            return code
    return 0


def run_logged(commands: Sequence[Command], log_path: Path) -> int:
    """Run `commands` in order with all their output in `log_path`; the first failure stops."""
    with log_path.open("wb") as log:
        for command in commands:
            code = _run(command, log)
            if code:
                return code
    return 0


def encodable(text: str, encoding: str) -> str:
    """`text` with what `encoding` cannot represent replaced, so a log tail never crashes a
    console that is not UTF-8 (a redirected Windows console uses the locale's code page)."""
    return text.encode(encoding, errors="replace").decode(encoding)


def log_tail(log_path: Path, lines: int) -> str:
    return "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


def run_step(step: Step, root: Path, log_dir: Path) -> None:
    """Run one step quietly: one line on success; on failure the log's tail and StepFailed."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{step.log_name}.log"
    print(f"==> {step.label:<44}", end="", flush=True)
    started = time.monotonic()
    code = run_logged(step.commands, log_path)
    if code == 0:
        print(f"ok ({int(time.monotonic() - started)}s)", flush=True)
        return
    print(f"FAILED (exit {code})", flush=True)
    tail = log_tail(log_path, FAILURE_TAIL_LINES)
    if tail:
        print(encodable(tail, sys.stderr.encoding or "utf-8"), file=sys.stderr)
    print(f"Full log: {log_path.relative_to(root)}", file=sys.stderr, flush=True)
    raise StepFailed(code)


# ---- prerequisites ---------------------------------------------------------------------------


def parse_port(text: str) -> int:
    """The explorer port. It reaches no shell, but anything but a port number is refused."""
    if not PORT_PATTERN.fullmatch(text) or not 1 <= int(text) <= MAX_PORT:
        raise PrerequisiteMissing(f"a numeric UI_PORT between 1 and {MAX_PORT}")
    return int(text)


def ui_port() -> int:
    """UI_PORT, or the default when unset or empty (make exports an unset variable as empty)."""
    return parse_port(os.environ.get(UI_PORT_ENV) or str(DEFAULT_UI_PORT))


def find_tool(name: str, hint: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise PrerequisiteMissing(hint)
    return found


def node_version(node: str) -> str:
    result = subprocess.run([node, "--version"], capture_output=True, text=True, check=False)
    return result.stdout.strip()


def node_major(version: str) -> int:
    major = version.removeprefix("v").split(".")[0]
    if not major.isascii() or not major.isdigit():
        raise PrerequisiteMissing(f"Node.js >= {MIN_NODE_MAJOR} (its version is unreadable)")
    return int(major)


def free_disk_bytes(root: Path) -> int:
    return shutil.disk_usage(root).free


def port_is_free(port: int) -> bool:
    """Whether the explorer can listen on `port`; checked first, so a busy port fails at once
    and not after the whole run."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((EXPLORER_HOST, port))
        except OSError:
            return False
    return True


def serve_command() -> str:
    """How to start the one command again, as a person on this OS types it."""
    return "uv run enron-case all" if ON_WINDOWS else "make"


def busy_port_hint() -> str:
    if ON_WINDOWS:
        return "stop what uses it, or set UI_PORT=<port> and run again"
    return "stop what uses it, or run: UI_PORT=<port> make"


def check_prerequisites(mode: str, port: int, root: Path) -> Tools:
    """Find uv, Node and npm, and check disk and port; raise PrerequisiteMissing naming the
    first thing missing. Python is the interpreter running this."""
    uv = find_tool(os.environ.get(UV_ENV) or "uv", UV_HINT)
    node = find_node()
    version = node_version(node)
    if node_major(version) < MIN_NODE_MAJOR:
        raise PrerequisiteMissing(f"Node.js >= {MIN_NODE_MAJOR} (found {version})")
    npm = find_tool("npm", "npm")
    free = free_disk_bytes(root)
    if free < MIN_FREE_DISK_BYTES:
        needed = MIN_FREE_DISK_BYTES // BYTES_PER_GB
        raise PrerequisiteMissing(
            f"{needed} GB free disk space (found {free / BYTES_PER_GB:.1f} GB)"
        )
    if mode == ALL and not port_is_free(port):
        raise PrerequisiteMissing(f"a free port {port} for the explorer ({busy_port_hint()})")
    python = f"Python {sys.version_info.major}.{sys.version_info.minor}"
    print(f"==> prerequisites: uv, {python}, Node {version}, npm", flush=True)
    return Tools(uv=uv, node=node, npm=npm)


# ---- the key ---------------------------------------------------------------------------------


def key_target() -> Path:
    """Where the one command creates a key when none is configured: KEY_FILE, else the default
    under the home directory (the user profile on Windows)."""
    named = os.environ.get(KEY_FILE_TARGET_ENV)
    return Path(named) if named else Path.home() / DEFAULT_KEY_PATH


def ensure_key(target: Path) -> None:
    """Create a key at `target` only when none is configured at all, then check the key every
    stage will use. A configured but unusable key raises KeyProblem and is never replaced."""
    if not os.environ.get(KEY_ENV) and not os.environ.get(KEY_FILE_ENV):
        if not target.exists():
            create_key_file(target)
            protection = "owner-only access" if ON_WINDOWS else "mode 600"
            print(f"==> key: none configured; created a new key at {target} ({protection})")
        os.environ[KEY_FILE_ENV] = str(target)  # so every stage reads the key just checked
    load_key_fingerprint(sample=False)
    print("==> key: usable key found (never printed)", flush=True)


# ---- the steps -------------------------------------------------------------------------------


def ui_dependency_commands(npm: str, ui_root: Path) -> tuple[Command, ...]:
    """`npm ci` when the installed UI dependencies are missing or older than the lockfile."""
    marker = ui_root / UI_DEPENDENCY_MARKER
    lockfile = ui_root / UI_LOCKFILE
    if marker.exists() and marker.stat().st_mtime >= lockfile.stat().st_mtime:
        return ()
    return (Command((npm, "ci"), ui_root),)


def python_gate(python: str, root: Path) -> tuple[Command, ...]:
    return tuple(Command((python, "-m", *tool), root) for tool in PYTHON_GATE)


def ui_gate(node: str, npm: str, ui_root: Path) -> tuple[Command, ...]:
    programs = {"npm": npm, "node": node}
    return tuple(Command((programs[tool[0]], *tool[1:]), ui_root) for tool in UI_GATE)


def install_step(tools: Tools, root: Path) -> Step:
    return Step(
        "install locked dependencies (uv, npm)",
        "install",
        (
            Command((tools.uv, "sync", "--locked"), root),
            *ui_dependency_commands(tools.npm, root / "ui"),
        ),
    )


def pipeline_steps(tools: Tools, root: Path) -> tuple[Step, ...]:
    """Every step after the key, in order."""
    ui_root = root / "ui"

    def cli(*args: str) -> tuple[Command, ...]:
        return (Command((tools.python, "-m", "enron_case", *args), root),)

    return (
        Step("download and verify the corpus", "fetch", cli("stage", "fetch")),
        Step("run the pipeline on the real corpus", "pipeline", cli("run")),
        Step("Python gate (lint, types, tests, canary)", "gate", python_gate(tools.python, root)),
        Step(
            "UI gate (lint, types, tests, build check)",
            "ui-gate",
            ui_gate(tools.node, tools.npm, ui_root),
        ),
        Step("export UI data from release/", "ui-data", cli("stage", "ui-data")),
        Step("build the explorer", "ui-build", (Command((tools.npm, "run", "build"), ui_root),)),
    )


def print_summary(mode: str, port: int, root: Path) -> None:
    log_dir = STEP_LOG_DIR.as_posix()
    print()
    print("All steps passed: pipeline, Python gate and UI gate are green.")
    print("  Report:   release/report.md")
    print(f"  Results:  {summary_line(Paths.for_run(root, sample=False).release_root)}")
    print(f"  Logs:     {log_dir}/")
    url = f"http://localhost:{port}"
    if mode == CHECK:
        print(f"  Explorer: built in ui/dist (run '{serve_command()}' to serve it at {url})")
    else:
        print(f"  Explorer: {url}  (Ctrl+C to stop)", flush=True)


def serve_explorer(tools: Tools, root: Path, port: int) -> int:
    """Serve the built explorer in the foreground until Ctrl+C."""
    preview = (tools.npm, "run", "preview", "--", "--port", str(port), "--strictPort")
    try:
        return run_streaming((Command(preview, root / "ui"),))
    except KeyboardInterrupt:
        return 0


def run_one_command(mode: str, root: Path = REPO_ROOT) -> int:
    """`all` or `check`; returns the exit code of the first failure, else 0 (or the server's)."""
    try:
        port = ui_port()
        tools = check_prerequisites(mode, port, root)
        log_dir = root / STEP_LOG_DIR
        run_step(install_step(tools, root), root, log_dir)
        ensure_key(key_target())
        for step in pipeline_steps(tools, root):
            run_step(step, root, log_dir)
        print_summary(mode, port, root)
    except PrerequisiteMissing as exc:
        print(f"==> missing prerequisite: {exc}", file=sys.stderr)
        return exc.exit_code
    except StepFailed as exc:
        return exc.exit_code
    except PipelineError as exc:
        stderr_log(f"error: {exc}")
        return exc.exit_code
    if mode == CHECK:
        return 0
    return serve_explorer(tools, root, port)


# ---- the gates and helpers on their own ------------------------------------------------------


def run_python_gate(root: Path = REPO_ROOT) -> int:
    return run_streaming(python_gate(sys.executable, root))


def find_node() -> str:
    return find_tool("node", f"Node.js >= {MIN_NODE_MAJOR}")


def install_ui_dependencies(root: Path = REPO_ROOT) -> int:
    return run_streaming(ui_dependency_commands(find_tool("npm", "npm"), root / "ui"))


def run_ui_gate(root: Path = REPO_ROOT) -> int:
    node, npm = find_node(), find_tool("npm", "npm")
    ui_root = root / "ui"
    return run_streaming((*ui_dependency_commands(npm, ui_root), *ui_gate(node, npm, ui_root)))


def create_key() -> None:
    """`make key`: create a key at the target unless one is there. Never prints the key."""
    target = key_target()
    if create_key_file(target):
        print(f"Key written to {target}")
    else:
        print(f"Key exists at {target}")


def run_helper(command: str) -> int:
    """`gate`, `ui-gate`, `ui-deps` and `key`; a missing tool is one named line, exit 1."""
    try:
        if command == "gate":
            return run_python_gate()
        if command == "ui-gate":
            return run_ui_gate()
        if command == "ui-deps":
            return install_ui_dependencies()
        create_key()
        return 0
    except PrerequisiteMissing as exc:
        print(f"==> missing prerequisite: {exc}", file=sys.stderr)
        return exc.exit_code
