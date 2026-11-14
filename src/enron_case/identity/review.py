"""T046: manual check of identity merges on the real corpus, by a person, in a terminal.

Shows a seeded sample of merged addresses next to the address they were merged into and asks
whether they are the same person. Identifiers are shown on screen only; they are never logged
or written. Only two counts leave the ingest zone: how many merges were checked and how many
were judged correct (`identity_manual` in the counts zone).
"""

from __future__ import annotations

from collections.abc import Callable

from enron_case.context import StageContext
from enron_case.identity.evaluate import MANUAL_SAMPLE_SIZE, manual_counts, sample_merges

COUNTS_NAME = "identity_manual"
YES, NO, SKIP = "y", "n", "s"

Ask = Callable[[str], str]
Show = Callable[[str], None]


def review(ctx: StageContext, ask: Ask = input, show: Show = print) -> tuple[int, int]:
    sample = sample_merges(ctx.read("address_map"), MANUAL_SAMPLE_SIZE, ctx.config.seed)
    show(
        f"{sample.height} merges to check. For each: is the address the same person as the "
        f"canonical address? [{YES}]es / [{NO}]o / [{SKIP}]kip (unsure)."
    )
    verdicts: list[bool] = []
    for index, row in enumerate(sample.iter_rows(named=True), start=1):
        prompt = f"{index:>2}. {row['addr']}  ->  {row['entity_id']}  (rule {row['rule']}) "
        answer = ""
        while answer not in {YES, NO, SKIP}:
            answer = ask(prompt).strip().lower()[:1]
        if answer != SKIP:
            verdicts.append(answer == YES)
    checked, correct = manual_counts(verdicts)
    ctx.write_counts(COUNTS_NAME, {"manual_checked": checked, "manual_correct": correct})
    return checked, correct
