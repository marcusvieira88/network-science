"""Stage `ui-data` (S10): export the release tables to `ui/public/data/release.json`."""

from __future__ import annotations

import json
from typing import Any

from enron_case.config import MANIFEST_FILE
from enron_case.context import StageContext
from enron_case.contracts import schemas
from enron_case.errors import ContractViolation
from enron_case.uiexport.export import (
    RELEASE_TABLES,
    build_document,
    check_no_identifiers,
    check_person_counts,
    render,
)
from enron_case.zones import Zone

UI_FILE = "release.json"


def read_manifest(ctx: StageContext) -> dict[str, Any]:
    path = ctx.path(Zone.RELEASE, MANIFEST_FILE, "r")
    if not path.exists():
        raise ContractViolation("run manifest has not been produced; run the pipeline first")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def run(ctx: StageContext) -> None:
    tables = {name: ctx.read(name) for name in RELEASE_TABLES}
    for name, df in tables.items():
        schemas.validate(df, name)
    check_person_counts(tables, ctx.config.k_min)
    document = build_document(tables, read_manifest(ctx))
    check_no_identifiers(document)
    text = render(document)
    ctx.path(Zone.UI, UI_FILE, "w").write_text(text, encoding="utf-8")
    rows = sum(df.height for df in tables.values())
    ctx.log(f"[ui-data] wrote {len(tables)} tables, {rows} rows")
