"""Outputs are byte-identical on every OS: every text write in src/ fixes its encoding and
writes "\\n" line endings (Python would write "\\r\\n" on Windows otherwise), and the
repository checks out with LF endings."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "enron_case"
REQUIRED = {"encoding": "utf-8", "newline": "\n"}
# `<module>.open(..., mode="w")` of these writes bytes whatever the mode string says.
BINARY_OPENERS = {"tarfile", "gzip", "bz2", "lzma", "zipfile"}


def keyword_constants(call: ast.Call) -> dict[str, object]:
    return {
        k.arg: k.value.value
        for k in call.keywords
        if k.arg is not None and isinstance(k.value, ast.Constant)
    }


def text_writes(tree: ast.AST) -> list[ast.Call]:
    """`x.write_text(...)` calls and `open(...)`/`x.open(...)` calls in a text write mode."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name == "write_text":
            found.append(node)
        elif name == "open" and not _binary_opener(func):
            modes = [a.value for a in node.args if isinstance(a, ast.Constant)]
            mode = keyword_constants(node).get("mode", modes[-1] if modes else "r")
            if isinstance(mode, str) and "b" not in mode and set(mode) & set("wax+"):
                found.append(node)
    return found


def _binary_opener(func: ast.expr) -> bool:
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in BINARY_OPENERS
    )


def unpinned_writes(source: str) -> list[int]:
    """Line numbers of text writes that do not pin encoding and newline."""
    return [
        call.lineno
        for call in text_writes(ast.parse(source))
        if any(keyword_constants(call).get(k) != v for k, v in REQUIRED.items())
    ]


@pytest.mark.parametrize(
    "path", sorted(SRC.rglob("*.py")), ids=lambda p: p.relative_to(SRC).as_posix()
)
def test_every_text_write_pins_encoding_and_newline(path: Path) -> None:
    lines = unpinned_writes(path.read_text(encoding="utf-8"))
    assert not lines, f"{path.relative_to(REPO_ROOT)}: lines {lines}"


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ("p.write_text(t)", [1]),
        ("p.write_text(t, encoding='utf-8')", [1]),
        ("p.write_text(t, encoding='utf-8', newline='\\n')", []),
        ("open(p, 'w')", [1]),
        ("p.open('a', encoding='utf-8')", [1]),
        ("p.open('w', encoding='utf-8', newline='\\n')", []),
        ("open(p, 'wb')", []),
        ("p.open('rb')", []),
        ("open(p)", []),
        ("tarfile.open(fileobj=b, mode='w')", []),
    ],
)
def test_checker_sees_unpinned_writes(source: str, flagged: list[int]) -> None:
    assert unpinned_writes(source) == flagged


def test_repository_checks_out_with_lf_endings() -> None:
    rules = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert "* text=auto eol=lf" in rules
