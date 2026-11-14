"""S9 report stage: release tables -> `release/report.md`, and documents with numbers injected.

Documents are written only on real-corpus runs; on the sample their numbers would describe
synthetic data. Templates live in `report/templates/` because the real-run documents zone is
`docs/` itself, so a template there would be overwritten by its own output.
"""

from __future__ import annotations

from enron_case.context import StageContext
from enron_case.report import render
from enron_case.report.templates import load_template
from enron_case.zones import Zone

REPORT_FILE = "report.md"
DOCUMENTS = ("decision-record.md", "slides.md", "ai-workflow.md")


def run(ctx: StageContext) -> None:
    tables = render.ReleaseTables.read(ctx)
    report = render.render_report(tables, ctx.config)
    ctx.path(Zone.RELEASE, REPORT_FILE, "w").write_text(report, encoding="utf-8", newline="\n")
    ctx.log(f"[report] wrote report with {report.count(chr(10))} lines")
    if ctx.sample:
        return
    values = render.document_values(tables, ctx.config)
    # Every document is scanned before any is written, as the report is, so a template or an
    # injected value holding an identifier stops the run with no document on disk.
    documents = {name: render.inject(load_template(name), values) for name in DOCUMENTS}
    for text in documents.values():
        render.check_no_identifiers(text)
    for name, text in documents.items():
        ctx.path(Zone.DOCS, name, "w").write_text(text, encoding="utf-8", newline="\n")
    ctx.log(f"[report] injected {len(values)} values into {len(DOCUMENTS)} documents")
