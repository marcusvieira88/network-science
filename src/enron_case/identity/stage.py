"""Stage S3 identity (T037): `messages` + `header_records` -> `entities`, `address_map`,
`identity_counts`. Logs counts only."""

from __future__ import annotations

from collections import Counter, defaultdict

import polars as pl

from enron_case.context import StageContext
from enron_case.contracts import schemas
from enron_case.contracts.counts import IdentityCounts
from enron_case.identity import classify, evaluate, rules
from enron_case.identity.resolve import Resolution, resolve


def run(ctx: StageContext) -> None:
    messages = ctx.read("messages")
    headers = ctx.read("header_records")
    occurrences = rules.address_occurrences(messages)
    candidates = rules.evidence(messages, headers, ctx.config.name_link_support)
    resolution = resolve(occurrences, candidates)
    amap = resolution.address_map
    entities = build_entities(
        amap,
        messages,
        rules.custodian_addresses(messages),
        ctx.config.recipient_cap,
        ctx.config.internal_domain,
    )
    ctx.write("address_map", amap)
    ctx.write("entities", entities)
    counts = identity_counts(resolution, entities, _scores(ctx, amap))
    ctx.write_counts("identity_counts", dict(counts))
    ctx.log(
        f"identity: {counts['addresses']} addresses -> {counts['entities']} entities; "
        f"merges {counts['merges_by_rule']}; blocked {counts['blocked_by_guard']}"
    )


def build_entities(
    amap: pl.DataFrame,
    messages: pl.DataFrame,
    custodian_addresses: set[str],
    recipient_cap: int,
    internal_domain: str,
) -> pl.DataFrame:
    entity_of = dict(amap.select("addr", "entity_id").iter_rows())
    behaviour = classify.entity_behaviour(messages, entity_of, recipient_cap)
    members: dict[str, list[str]] = defaultdict(list)
    for addr, entity in entity_of.items():
        members[entity].append(addr)
    custodians = {entity_of[a] for a in custodian_addresses if a in entity_of}
    rows = []
    for entity, addrs in sorted(members.items()):
        org = rules.registered_domain(entity)
        rows.append(
            {
                "entity_id": entity,
                "type": classify.entity_type(sorted(addrs), behaviour[entity]),
                "org_domain": org,
                "is_internal": org == internal_domain,
                "is_custodian": entity in custodians,
                "n_addresses": len(addrs),
            }
        )
    df = pl.DataFrame(rows, schema=schemas.table("entities").polars_schema)
    return schemas.conform(df, "entities")


def identity_counts(
    resolution: Resolution,
    entities: pl.DataFrame,
    scores: tuple[float | None, float | None],
) -> IdentityCounts:
    amap = resolution.address_map
    merges = Counter(r for r in amap.get_column("rule").to_list() if r is not None)
    sizes = Counter(entities.get_column("n_addresses").to_list())
    types = Counter(entities.get_column("type").to_list())
    return {
        "addresses": amap.height,
        "entities": entities.height,
        "entities_by_type": dict(sorted(types.items())),
        "merges_by_rule": dict(sorted(merges.items())),
        "blocked_by_guard": resolution.blocked_by_guard,
        "cluster_sizes": {str(k): v for k, v in sorted(sizes.items())},
        "precision": scores[0],
        "recall": scores[1],
        "manual_checked": None,
        "manual_correct": None,
    }


def _scores(ctx: StageContext, amap: pl.DataFrame) -> tuple[float | None, float | None]:
    if not ctx.has_truth():
        return None, None
    entity_of = dict(amap.select("addr", "entity_id").iter_rows())
    return evaluate.pairwise_scores(entity_of, ctx.read_truth()["address_to_truth"])
