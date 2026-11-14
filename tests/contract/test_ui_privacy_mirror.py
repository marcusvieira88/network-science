"""The explorer's own privacy guard (ui/src/lib/privacy.ts) must mirror the Python rules.

TypeScript cannot import the Python constants, so this test reads the TypeScript source and
compares each mirrored value with its single Python definition.
"""

from __future__ import annotations

import re
from pathlib import Path

from enron_case.config import Config
from enron_case.contracts import schemas, vocab
from enron_case.uiexport.export import RELEASE_TABLES

PRIVACY_TS = Path(__file__).resolve().parents[2] / "ui" / "src" / "lib" / "privacy.ts"


def _source() -> str:
    return PRIVACY_TS.read_text(encoding="utf-8")


def _constant(name: str) -> str:
    found = re.search(rf"^(?:export )?const {name} = (.+);$", _source(), re.MULTILINE)
    assert found, name
    return found.group(1)


def test_leak_pattern_matches_vocab() -> None:
    found = re.search(r"^export const LEAK_PATTERN = /(.+)/;$", _source(), re.MULTILINE)
    assert found
    assert found.group(1) == "|".join(vocab.LEAK_PATTERNS)


def test_k_floor_matches_config() -> None:
    assert int(_constant("K_FLOOR")) == Config().k_min


def test_person_count_metric_matches_schemas() -> None:
    assert _constant("PERSON_COUNT_METRIC") == f'"{schemas.PERSON_COUNT_METRIC}"'


def test_person_count_columns_match_schemas_for_exported_tables() -> None:
    block = re.search(r"PERSON_COUNT_COLUMNS = \{(.*?)\} as const;", _source(), re.DOTALL)
    assert block
    mirrored = {
        table: tuple(re.findall(r'"([a-z_]+)"', columns))
        for table, columns in re.findall(r"(\w+): \[([^\]]*)\]", block.group(1))
    }
    expected = {
        table: columns
        for table, columns in schemas.PERSON_COUNT_COLUMNS.items()
        if table in RELEASE_TABLES
    }
    assert mirrored == expected
