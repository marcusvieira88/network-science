"""Shape of the synthetic ground truth (`truth/truth.json`, sample corpus only).

Written by `synth.fixtures.FixtureBuilder.truth`, read by `StageContext.read_truth` and the
tests. All names and addresses in it are invented.
"""

from __future__ import annotations

from typing import TypedDict


class TruthSpec(TypedDict):
    seed: int
    planted_change: bool
    change_week: str  # ISO date
    domain: str


class TruthEntity(TypedDict):
    truth_id: str
    entity_id: str | None  # None when the entity never appears in a header
    type: str
    addresses: list[str]
    display_name: str
    org_domain: str
    is_internal: bool
    is_custodian: bool
    owner_dir: str | None
    community: int


class GroundTruth(TypedDict):
    spec: TruthSpec
    entities: list[TruthEntity]
    address_to_truth: dict[str, str]
    file_to_message: dict[str, str]
    hubs: list[str]
    canary_markers: list[str]
    owner_dirs: list[str]
    display_names: list[str]
    bad_addresses: list[str]
    n_messages: int
    n_files: int
