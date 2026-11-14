"""T046: manual check of identity merges on the real corpus, by a person, in a terminal.

Shows a seeded sample of merged addresses next to the address they were merged into and asks
whether they are the same person. Identifiers are shown on screen only; they are never logged
or written. Only counts leave the ingest zone: how many merges were checked and how many were
judged correct, in total and per identity rule (`identity_manual` in the counts zone).
"""

from __future__ import annotations

from collections.abc import Callable

from enron_case.context import StageContext
from enron_case.identity.evaluate import manual_counts, manual_counts_by_rule, sample_merges

COUNTS_NAME = "identity_manual"
YES, NO, SKIP = "y", "n", "s"

Ask = Callable[[str], str]
Show = Callable[[str], None]


def review(ctx: StageContext, ask: Ask = input, show: Show = print) -> tuple[int, int]:
    sample = sample_merges(ctx.read("address_map"), ctx.config.manual_sample_size, ctx.config.seed)
    show(
        f"{sample.height} merges to check. For each: is the address the same person as the "
        f"canonical address? [{YES}]es / [{NO}]o / [{SKIP}]kip (unsure)."
    )
    rules: list[str] = []
    verdicts: list[bool | None] = []
    for index, row in enumerate(sample.iter_rows(named=True), start=1):
        prompt = f"{index:>2}. {row['addr']}  ->  {row['entity_id']}  (rule {row['rule']}) "
        answer = ""
        while answer not in {YES, NO, SKIP}:
            answer = ask(prompt).strip().lower()[:1]
        rules.append(row["rule"])
        verdicts.append(None if answer == SKIP else answer == YES)
    checked, correct = manual_counts([v for v in verdicts if v is not None])
    counts = {
        "manual_checked": checked,
        "manual_correct": correct,
        "manual_by_rule": manual_counts_by_rule(rules, verdicts),
    }
    ctx.write_counts(COUNTS_NAME, counts)
    ctx.write_check(COUNTS_NAME, counts)
    return checked, correct
