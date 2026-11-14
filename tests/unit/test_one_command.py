"""The one command (contracts/cli.md): `enron-case all|check` runs the same steps on every OS,
each step's exit code stops the run, prerequisites fail with one named line, the gates are
defined once, and the summary counts hypotheses held true from the release tables."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from enron_case import config, onecommand
from enron_case.cli import main, summary_line
from enron_case.errors import KeyProblem, PipelineError, PrerequisiteMissing, StepFailed
from enron_case.onecommand import Command, Step, Tools
from helpers import TEST_KEY_HEX

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "gate.yml"
FAKE_TOOLS = Tools(uv="uv", node="node", npm="npm", python=sys.executable)
NODE_TOO_OLD = "v18.19.0"
NODE_OK = "v22.15.1"
CHILD_LINES = 50  # more than the failure tail shows

HYPOTHESES_CSV = "hypothesis,is_headline\nH1,false\nH2,true\nH3,false\nH4,false\n"
EXPLORATORY_CSV = (
    "hypothesis,outcome\nH5,confident\nH6,not supported\nH7,inconclusive\nH8,confident\n"
)


def _write_release(root: Path, hypotheses: str, exploratory: str) -> Path:
    root.mkdir()
    (root / "hypotheses.csv").write_text(hypotheses, encoding="utf-8")
    (root / "exploratory.csv").write_text(exploratory, encoding="utf-8")
    return root


def python_command(code: str, cwd: Path) -> Command:
    return Command((sys.executable, "-c", code), cwd)


def unset_env(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Unset `names` for this test only, also when the code under test sets them again."""
    for name in names:
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


# ---- make and CI are thin wrappers over one definition ---------------------------------------


def test_makefile_default_goal_is_all() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert ".DEFAULT_GOAL := all" in makefile.splitlines()


@pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")
def test_bare_make_runs_the_same_recipe_as_make_all() -> None:
    def dry_run(*goal: str) -> str:
        return subprocess.run(
            ["make", "-n", *goal], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout

    assert dry_run() == dry_run("all")
    assert "enron-case all" in dry_run()


@pytest.mark.parametrize("wrapper", ["Makefile", ".github/workflows/gate.yml", "run.cmd"])
def test_wrappers_hold_no_gate_step_of_their_own(wrapper: str) -> None:
    """The gate steps live in config.py only; make, CI and run.cmd call `enron-case`."""
    text = (REPO_ROOT / wrapper).read_text(encoding="utf-8")
    assert "enron-case" in text
    for program in ("ruff", "mypy", "pytest", "npm run lint", "check-build"):
        assert program not in text, f"{wrapper} runs {program} itself"


def test_python_gate_runs_each_tool_as_a_module_of_this_interpreter() -> None:
    commands = onecommand.python_gate(sys.executable, REPO_ROOT)
    assert [c.argv for c in commands] == [
        (sys.executable, "-m", "ruff", "check", "src", "tests"),
        (sys.executable, "-m", "ruff", "format", "--check", "src", "tests"),
        (sys.executable, "-m", "mypy"),
        (sys.executable, "-m", "pytest", "-q"),
    ]
    assert {c.cwd for c in commands} == {REPO_ROOT}


def test_ui_gate_uses_the_resolved_npm_and_node(tmp_path: Path) -> None:
    """On Windows npm is npm.cmd; the gate uses whatever path shutil.which found."""
    commands = onecommand.ui_gate(r"C:\node\node.exe", r"C:\node\npm.cmd", tmp_path)
    assert commands[0].argv == (r"C:\node\npm.cmd", "run", "lint")
    assert commands[-1].argv == (r"C:\node\node.exe", "scripts/check-build.mjs")
    assert len(commands) == len(config.UI_GATE)
    assert {c.cwd for c in commands} == {tmp_path}


def test_ci_runs_every_os_and_never_the_real_corpus() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for runner in ("ubuntu-latest", "macos-latest", "windows-latest"):
        assert runner in text
    assert "enron-case gate" in text
    assert "enron-case ui-gate" in text
    assert "run --sample" in text
    for real_run in ("enron-case all", "enron-case check", "make check", "stage fetch"):
        assert real_run not in text


# ---- the step runner -------------------------------------------------------------------------


def test_step_success_prints_one_line_and_logs_the_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    step = Step("say hello", "hello", (python_command("print('hello from the step')", tmp_path),))
    onecommand.run_step(step, tmp_path, tmp_path / "logs")
    out = capsys.readouterr().out
    assert out.startswith("==> say hello")
    assert out.rstrip().endswith("s)")
    assert "ok (" in out
    log = (tmp_path / "logs" / "hello.log").read_text(encoding="utf-8")
    assert "hello from the step" in log


def test_failing_step_raises_its_own_exit_code_and_shows_the_log_tail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = f"import sys\nfor i in range({CHILD_LINES}): print(f'line {{i}}')\nsys.exit(3)"
    step = Step("fail", "fail", (python_command(code, tmp_path),))
    with pytest.raises(StepFailed) as raised:
        onecommand.run_step(step, tmp_path, tmp_path / "data" / "logs")
    assert raised.value.exit_code == 3
    captured = capsys.readouterr()
    assert "FAILED (exit 3)" in captured.out
    shown = captured.err.splitlines()
    assert f"line {CHILD_LINES - 1}" in shown
    assert f"line {CHILD_LINES - config.FAILURE_TAIL_LINES - 1}" not in shown
    assert f"line {CHILD_LINES - config.FAILURE_TAIL_LINES}" in shown
    assert shown[-1] == "Full log: " + str(Path("data", "logs", "fail.log"))


def test_first_failing_command_stops_the_step(tmp_path: Path) -> None:
    marker = tmp_path / "second-ran"
    step = Step(
        "two commands",
        "two",
        (
            python_command("import sys; sys.exit(4)", tmp_path),
            python_command(f"open({str(marker)!r}, 'w').close()", tmp_path),
        ),
    )
    with pytest.raises(StepFailed) as raised:
        onecommand.run_step(step, tmp_path, tmp_path / "logs")
    assert raised.value.exit_code == 4
    assert not marker.exists()


@pytest.mark.parametrize(("returncode", "status"), [(0, 0), (3, 3), (-2, 130), (-9, 137)])
def test_signal_deaths_map_to_shell_exit_codes(returncode: int, status: int) -> None:
    assert onecommand.exit_status(returncode) == status


def test_streamed_commands_return_the_first_failure(tmp_path: Path) -> None:
    commands = (
        python_command("pass", tmp_path),
        python_command("import sys; sys.exit(5)", tmp_path),
        python_command("import sys; sys.exit(6)", tmp_path),
    )
    assert onecommand.run_streaming(commands) == 5
    assert onecommand.run_streaming(commands[:1]) == 0


def test_log_tail_survives_a_console_that_cannot_encode_it() -> None:
    assert onecommand.encodable("ok ✓ ≥", "cp1252") == "ok ? ?"
    assert onecommand.encodable("ok ✓ ≥", "utf-8") == "ok ✓ ≥"


# ---- prerequisites ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["4173", "1", "65535"])
def test_numeric_port_is_accepted(text: str) -> None:
    assert onecommand.parse_port(text) == int(text)


@pytest.mark.parametrize("text", ["abc", "4173; rm -rf /", "0", "65536", "99999", "²", "-1"])
def test_bad_port_is_a_missing_prerequisite(text: str) -> None:
    with pytest.raises(PrerequisiteMissing, match="numeric UI_PORT") as raised:
        onecommand.parse_port(text)
    assert raised.value.exit_code == 1


def test_port_defaults_when_unset_or_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(config.UI_PORT_ENV, "")  # make exports an unset variable as empty
    assert onecommand.ui_port() == config.DEFAULT_UI_PORT
    monkeypatch.setenv(config.UI_PORT_ENV, "4184")
    assert onecommand.ui_port() == 4184


@pytest.mark.parametrize(("text", "major"), [("v20.11.1", 20), ("v8.0.0", 8), ("22.1.0", 22)])
def test_node_major_version(text: str, major: int) -> None:
    assert onecommand.node_major(text) == major


def test_unreadable_node_version_is_a_missing_prerequisite() -> None:
    with pytest.raises(PrerequisiteMissing):
        onecommand.node_major("node: command failed")


def test_busy_port_is_detected() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind((config.EXPLORER_HOST, 0))
        server.listen()
        port = server.getsockname()[1]
        assert not onecommand.port_is_free(port)
    assert onecommand.port_is_free(port)


Which = Callable[[str], str | None]


def fake_which(missing: str = "") -> Which:
    def which(name: str) -> str | None:
        return None if name == missing else f"/opt/bin/{name}"

    return which


@pytest.fixture
def healthy_machine(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Every tool present, Node new enough, plenty of disk; tests break one thing each."""
    monkeypatch.setattr("enron_case.onecommand.shutil.which", fake_which())
    monkeypatch.setattr(onecommand, "node_version", lambda node: NODE_OK)
    monkeypatch.setattr(onecommand, "free_disk_bytes", lambda root: config.MIN_FREE_DISK_BYTES)
    monkeypatch.setattr(onecommand, "port_is_free", lambda port: True)
    unset_env(monkeypatch, config.UV_ENV)
    return monkeypatch


def test_healthy_machine_passes_and_names_its_tools(
    healthy_machine: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tools = onecommand.check_prerequisites(onecommand.ALL, 4173, REPO_ROOT)
    assert tools == Tools("/opt/bin/uv", "/opt/bin/node", "/opt/bin/npm", sys.executable)
    assert capsys.readouterr().out == f"==> prerequisites: uv, Python 3.12, Node {NODE_OK}, npm\n"


def test_uv_from_its_environment_variable_is_used(healthy_machine: pytest.MonkeyPatch) -> None:
    """`uv run` tells its child where uv is; that one is used."""
    healthy_machine.setenv(config.UV_ENV, "/elsewhere/uv")
    healthy_machine.setattr("enron_case.onecommand.shutil.which", lambda name: name)
    tools = onecommand.check_prerequisites(onecommand.CHECK, 4173, REPO_ROOT)
    assert tools.uv == "/elsewhere/uv"


@pytest.mark.parametrize(
    ("missing", "message"),
    [
        ("uv", "uv (https://docs.astral.sh/uv/)"),
        (
            "node",
            "Node.js >= 20 (install it from https://nodejs.org, or on macOS: brew install node)",
        ),
        ("npm", "npm (it comes with Node.js: https://nodejs.org)"),
    ],
)
def test_missing_tool_is_named(
    healthy_machine: pytest.MonkeyPatch, missing: str, message: str
) -> None:
    healthy_machine.setattr("enron_case.onecommand.shutil.which", fake_which(missing))
    with pytest.raises(PrerequisiteMissing) as raised:
        onecommand.check_prerequisites(onecommand.CHECK, 4173, REPO_ROOT)
    assert str(raised.value) == message
    assert raised.value.exit_code == 1


def test_old_node_is_named_with_its_version(healthy_machine: pytest.MonkeyPatch) -> None:
    healthy_machine.setattr(onecommand, "node_version", lambda node: NODE_TOO_OLD)
    with pytest.raises(PrerequisiteMissing) as raised:
        onecommand.check_prerequisites(onecommand.CHECK, 4173, REPO_ROOT)
    assert str(raised.value) == f"Node.js >= 20 (found {NODE_TOO_OLD})"


def test_low_disk_is_named_with_what_is_free(healthy_machine: pytest.MonkeyPatch) -> None:
    healthy_machine.setattr(onecommand, "free_disk_bytes", lambda root: 1024**3)
    with pytest.raises(PrerequisiteMissing) as raised:
        onecommand.check_prerequisites(onecommand.CHECK, 4173, REPO_ROOT)
    assert str(raised.value) == "3 GB free disk space (found 1.0 GB)"


def test_busy_port_stops_all_but_not_check(healthy_machine: pytest.MonkeyPatch) -> None:
    healthy_machine.setattr(onecommand, "port_is_free", lambda port: False)
    healthy_machine.setattr(onecommand, "ON_WINDOWS", False)
    with pytest.raises(PrerequisiteMissing) as raised:
        onecommand.check_prerequisites(onecommand.ALL, 4184, REPO_ROOT)
    assert str(raised.value) == (
        "a free port 4184 for the explorer (stop what uses it, or run: UI_PORT=<port> make)"
    )
    onecommand.check_prerequisites(onecommand.CHECK, 4184, REPO_ROOT)


def test_busy_port_hint_on_windows_needs_no_make(healthy_machine: pytest.MonkeyPatch) -> None:
    healthy_machine.setattr(onecommand, "port_is_free", lambda port: False)
    healthy_machine.setattr(onecommand, "ON_WINDOWS", True)
    with pytest.raises(PrerequisiteMissing) as raised:
        onecommand.check_prerequisites(onecommand.ALL, 4184, REPO_ROOT)
    assert "make" not in str(raised.value)
    assert "UI_PORT" in str(raised.value)


# ---- UI dependencies -------------------------------------------------------------------------


def test_ui_dependencies_install_when_missing_or_older_than_the_lockfile(tmp_path: Path) -> None:
    (tmp_path / config.UI_LOCKFILE).write_text("{}", encoding="utf-8")
    assert onecommand.ui_dependency_commands("npm", tmp_path) == (Command(("npm", "ci"), tmp_path),)
    marker = tmp_path / config.UI_DEPENDENCY_MARKER
    marker.parent.mkdir()
    marker.write_text("{}", encoding="utf-8")
    lock_time = (tmp_path / config.UI_LOCKFILE).stat().st_mtime
    os.utime(marker, (lock_time - 10, lock_time - 10))
    assert len(onecommand.ui_dependency_commands("npm", tmp_path)) == 1
    os.utime(marker, (lock_time + 10, lock_time + 10))
    assert onecommand.ui_dependency_commands("npm", tmp_path) == ()


# ---- the key ---------------------------------------------------------------------------------


def fake_create(created: list[Path]) -> Callable[[Path], bool]:
    def create(path: Path) -> bool:
        created.append(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("cd" * 32 + "\n", encoding="utf-8")
        path.chmod(config.KEY_FILE_MODE)
        return True

    return create


def test_key_is_created_when_none_is_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    unset_env(monkeypatch, config.KEY_ENV, config.KEY_FILE_ENV)
    created: list[Path] = []
    monkeypatch.setattr(onecommand, "create_key_file", fake_create(created))
    target = tmp_path / "home" / "key"
    onecommand.ensure_key(target)
    assert created == [target]
    assert os.environ[config.KEY_FILE_ENV] == str(target)
    out = capsys.readouterr().out
    assert f"created a new key at {target}" in out
    assert "usable key found (never printed)" in out
    assert "cd" * 32 not in out


def test_existing_key_file_is_reused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    unset_env(monkeypatch, config.KEY_ENV, config.KEY_FILE_ENV)
    target = tmp_path / "key"
    fake_create([])(target)
    created: list[Path] = []
    monkeypatch.setattr(onecommand, "create_key_file", fake_create(created))
    onecommand.ensure_key(target)
    assert created == []


def test_configured_unusable_key_is_never_replaced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(config.KEY_ENV, "ab" * 16)  # too short
    created: list[Path] = []
    monkeypatch.setattr(onecommand, "create_key_file", fake_create(created))
    with pytest.raises(KeyProblem):
        onecommand.ensure_key(tmp_path / "key")
    assert created == []
    assert not (tmp_path / "key").exists()


def test_sample_key_is_refused_for_the_real_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(config.KEY_ENV, TEST_KEY_HEX)
    with pytest.raises(KeyProblem):
        onecommand.ensure_key(Path("unused"))


def test_key_target_defaults_to_the_home_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(config.KEY_FILE_TARGET_ENV, "")
    assert onecommand.key_target() == Path.home() / config.DEFAULT_KEY_PATH
    monkeypatch.setenv(config.KEY_FILE_TARGET_ENV, "/other/key")
    assert onecommand.key_target() == Path("/other/key")


# ---- the whole run ---------------------------------------------------------------------------


@pytest.fixture
def recorded_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    """A run whose prerequisites and key pass and whose steps only record their log names."""
    ran: list[str] = []

    def record(step: Step, root: Path, log_dir: Path) -> None:
        ran.append(step.log_name)

    monkeypatch.setattr(onecommand, "check_prerequisites", lambda mode, port, root: FAKE_TOOLS)
    monkeypatch.setattr(onecommand, "ensure_key", lambda target: ran.append("key"))
    monkeypatch.setattr(onecommand, "run_step", record)
    monkeypatch.setattr(onecommand, "summary_line", lambda release: "3 of 8 hypotheses held true")
    monkeypatch.setattr(onecommand, "serve_explorer", lambda tools, root, port: 0)
    return ran


def test_check_runs_every_step_in_order_and_exits_0(
    recorded_run: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert onecommand.run_one_command(onecommand.CHECK, tmp_path) == 0
    assert recorded_run == [
        "install",
        "key",
        "fetch",
        "pipeline",
        "gate",
        "ui-gate",
        "ui-data",
        "ui-build",
    ]
    out = capsys.readouterr().out
    assert "All steps passed: pipeline, Python gate and UI gate are green." in out
    assert "  Results:  3 of 8 hypotheses held true" in out
    assert "  Explorer: built in ui/dist" in out


def test_all_serves_after_the_summary(
    recorded_run: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    served: list[int] = []

    def serve(tools: Tools, root: Path, port: int) -> int:
        served.append(port)
        return 0

    monkeypatch.setattr(onecommand, "serve_explorer", serve)
    monkeypatch.setenv(config.UI_PORT_ENV, "4184")
    assert onecommand.run_one_command(onecommand.ALL, tmp_path) == 0
    assert served == [4184]


def test_failing_step_stops_the_run_with_its_code(
    recorded_run: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_at_fetch(step: Step, root: Path, log_dir: Path) -> None:
        recorded_run.append(step.log_name)
        if step.log_name == "fetch":
            raise StepFailed(4)

    monkeypatch.setattr(onecommand, "run_step", fail_at_fetch)
    assert onecommand.run_one_command(onecommand.CHECK, tmp_path) == 4
    assert recorded_run == ["install", "key", "fetch"]


def test_missing_prerequisite_exits_1_with_one_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def missing(mode: str, port: int, root: Path) -> Tools:
        raise PrerequisiteMissing("npm")

    monkeypatch.setattr(onecommand, "check_prerequisites", missing)
    assert onecommand.run_one_command(onecommand.CHECK, tmp_path) == 1
    assert capsys.readouterr().err == "==> missing prerequisite: npm\n"


def test_key_problem_exits_3_before_the_corpus(
    recorded_run: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unusable(target: Path) -> None:
        raise KeyProblem("no key found (default key file missing); run: make key")

    monkeypatch.setattr(onecommand, "ensure_key", unusable)
    assert onecommand.run_one_command(onecommand.CHECK, tmp_path) == 3
    assert recorded_run == ["install"]
    assert "error: no key found" in capsys.readouterr().err


def test_cli_routes_the_one_command(monkeypatch: pytest.MonkeyPatch) -> None:
    modes: list[str] = []

    def run(mode: str, root: Path = REPO_ROOT) -> int:
        modes.append(mode)
        return 7

    monkeypatch.setattr(onecommand, "run_one_command", run)
    assert main(["check"]) == 7
    assert main(["all"]) == 7
    assert modes == ["check", "all"]


# ---- the summary -----------------------------------------------------------------------------


def test_summary_counts_headline_and_confident_outcomes(tmp_path: Path) -> None:
    release = _write_release(tmp_path / "release", HYPOTHESES_CSV, EXPLORATORY_CSV)
    assert summary_line(release) == "3 of 8 hypotheses held true"


def test_summary_counts_zero_when_nothing_is_held_true(tmp_path: Path) -> None:
    hypotheses = HYPOTHESES_CSV.replace("true\n", "false\n")
    exploratory = "hypothesis,outcome\nH5,inconclusive\n"
    release = _write_release(tmp_path / "release", hypotheses, exploratory)
    assert summary_line(release) == "0 of 5 hypotheses held true"


def test_summary_command_fails_loudly_without_a_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("enron_case.cli.REPO_ROOT", tmp_path)
    assert main(["summary"]) == PipelineError.exit_code
