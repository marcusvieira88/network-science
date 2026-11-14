"""The one command (contracts/cli.md): bare `make` runs `all`, the scripts parse, and the
summary line counts hypotheses held true from the release tables."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from enron_case.cli import main, summary_line
from enron_case.errors import PipelineError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ("scripts/run-all.sh", "scripts/create-key.sh")

HYPOTHESES_CSV = "hypothesis,is_headline\nH1,false\nH2,true\nH3,false\nH4,false\n"
EXPLORATORY_CSV = (
    "hypothesis,outcome\nH5,confident\nH6,not supported\nH7,inconclusive\nH8,confident\n"
)


def _write_release(root: Path, hypotheses: str, exploratory: str) -> Path:
    root.mkdir()
    (root / "hypotheses.csv").write_text(hypotheses, encoding="utf-8")
    (root / "exploratory.csv").write_text(exploratory, encoding="utf-8")
    return root


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
    assert "scripts/run-all.sh all" in dry_run()


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_passes_bash_syntax_check(script: str) -> None:
    result = subprocess.run(
        ["bash", "-n", str(REPO_ROOT / script)], check=False, capture_output=True
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_is_strict_and_executable(script: str) -> None:
    path = REPO_ROOT / script
    assert "set -euo pipefail" in path.read_text(encoding="utf-8")
    assert path.stat().st_mode & 0o111


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
