"""Packages after the pseudonymization boundary must not import ingest-side packages."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "enron_case"
INGEST_SIDE = {"ingest", "clean", "identity"}
DOWNSTREAM = ("network", "finding", "risk", "release", "report", "uiexport")
STRING_IMPORTERS = {"import_module", "__import__"}
UIEXPORT_ALLOWED = {"zones", "config", "contracts", "context", "errors", "uiexport"}


def imported_packages(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        elif _is_string_import(node):
            names = [_first_string(node)]
        for name in names:
            parts = name.split(".")
            if parts[0] == "enron_case" and len(parts) > 1:
                found.add(parts[1])
    return found


def _is_string_import(node: ast.AST) -> bool:
    """`import_module("enron_case.x")` or `importlib.import_module(...)` with a literal name."""
    if not isinstance(node, ast.Call) or not node.args:
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    first = node.args[0]
    return (
        name in STRING_IMPORTERS
        and isinstance(first, ast.Constant)
        and isinstance(first.value, str)
    )


def _first_string(node: ast.AST) -> str:
    assert isinstance(node, ast.Call)
    first = node.args[0]
    assert isinstance(first, ast.Constant)
    return str(first.value)


@pytest.mark.parametrize("package", DOWNSTREAM)
def test_downstream_does_not_import_ingest_side(package: str) -> None:
    for path in (SRC / package).rglob("*.py"):
        bad = imported_packages(path) & INGEST_SIDE
        assert not bad, f"{path.relative_to(SRC)} imports {sorted(bad)}"


def test_uiexport_imports_only_release_side_helpers() -> None:
    for path in (SRC / "uiexport").rglob("*.py"):
        bad = imported_packages(path) - UIEXPORT_ALLOWED
        assert not bad, f"{path.relative_to(SRC)} imports {sorted(bad)}"


def test_checker_sees_imports(tmp_path: Path) -> None:
    sample = tmp_path / "x.py"
    sample.write_text(
        "from enron_case.ingest import parse\nimport enron_case.clean.dedupe\n"
        "import importlib\nimportlib.import_module('enron_case.identity.rules')\n"
    )
    assert imported_packages(sample) == {"ingest", "clean", "identity"}


# The attacker sees a release and its own auxiliary knowledge only: its modules may import
# nothing from this project except each other, so no path leads to the scorer, the address map,
# the key, the zones or the ground truth.
ATTACKER_MODULES = ("attack.py", "features.py")
ATTACKER_ALLOWED = {"enron_case.risk.attack", "enron_case.risk.features"}


def imported_modules(path: Path) -> set[str]:
    """Full names of the project modules a file imports, string imports included."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.update(f"{node.module}.{a.name}" for a in node.names)
            found.add(node.module)
        elif _is_string_import(node):
            found.add(_first_string(node))
    return {name for name in found if name.startswith("enron_case")}


def _outside_attacker(module: str) -> bool:
    # `from enron_case.risk.features import NODE` yields the module and module.NODE.
    return not any(module == m or module.startswith(f"{m}.") for m in ATTACKER_ALLOWED)


@pytest.mark.parametrize("module", ATTACKER_MODULES)
def test_attacker_imports_nothing_that_reaches_the_truth(module: str) -> None:
    bad = sorted(m for m in imported_modules(SRC / "risk" / module) if _outside_attacker(m))
    assert not bad, f"risk/{module} imports {bad}"


def test_attacker_checker_sees_a_path_to_the_scorer(tmp_path: Path) -> None:
    sample = tmp_path / "x.py"
    sample.write_text(
        "from enron_case.risk.features import NODE\nfrom enron_case.risk import score\n"
        "import enron_case.context\n"
    )
    bad = sorted(m for m in imported_modules(sample) if _outside_attacker(m))
    assert bad == ["enron_case.context", "enron_case.risk", "enron_case.risk.score"]
