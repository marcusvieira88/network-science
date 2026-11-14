"""Stage S4: cross the pseudonymization boundary (ingest zone -> restricted zone)."""

from __future__ import annotations

from enron_case.context import StageContext
from enron_case.contracts.counts import PseudoCounts
from enron_case.pseudo.keys import load_run_key
from enron_case.pseudo.pseudonymize import build_entities_p, build_events


def run(ctx: StageContext) -> None:
    key = load_run_key(ctx.sample)
    messages = ctx.read("messages")
    entities = ctx.read("entities")
    events = ctx.write("events", build_events(key, messages, entities, ctx.read("address_map")))
    ctx.write("entities_p", build_entities_p(key, entities))
    counts = PseudoCounts(
        entities=entities.height,
        events=events.height,
        messages_without_time=messages["ts_utc"].null_count(),
        events_in_network=int(events["in_network"].sum()),
    )
    ctx.write_counts("pseudo_counts", dict(counts))
    ctx.log(
        f"[pseudo] {counts['entities']} entities, {counts['events']} events, "
        f"{counts['events_in_network']} in network, "
        f"{counts['messages_without_time']} messages without time"
    )
