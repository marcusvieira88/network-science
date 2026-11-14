from __future__ import annotations

import gzip
import hashlib
import tarfile
from pathlib import Path

from enron_case.contracts import schemas
from enron_case.manifest import fingerprint
from enron_case.synth import SynthOutput, generate


def test_same_seed_same_output(synth: SynthOutput, tmp_path: Path) -> None:
    again = generate(tmp_path)
    assert (
        hashlib.sha256(again.archive.read_bytes()).digest()
        == hashlib.sha256(synth.archive.read_bytes()).digest()
    )
    for name in schemas.TABLES:
        assert fingerprint(again.table(name)) == fingerprint(synth.table(name)), name


def test_archive_matches_ground_truth(synth: SynthOutput) -> None:
    truth = synth.truth()
    with tarfile.open(synth.archive) as tar:
        members = [m.name for m in tar.getmembers() if m.isfile()]
    assert sorted(members) == sorted(truth["file_to_message"])
    assert synth.table("header_records").height == len(members) == truth["n_files"]
    assert synth.table("messages").height == truth["n_messages"]


def test_planted_structures_exist(synth: SynthOutput) -> None:
    messages = synth.table("messages")
    rules = set(messages.get_column("dedupe_rule").to_list())
    assert rules == {"none", "exact", "subset"}
    flags = set(messages.get_column("flags").explode().drop_nulls().to_list())
    assert flags == {
        "date_out_of_range",
        "no_recipients",
        "self_only",
        "mass_mailing",
        "bad_address",
    }
    assert set(synth.table("address_map").get_column("rule").drop_nulls().to_list()) == {"N2", "N3"}


def test_archive_carries_canaries(synth: SynthOutput) -> None:
    text = gzip.decompress(synth.archive.read_bytes()).decode("latin-1")
    for marker in synth.truth()["canary_markers"]:
        assert marker in text


def test_no_change_variant_differs_only_in_change(
    synth: SynthOutput, synth_nochange: SynthOutput
) -> None:
    assert synth.truth()["spec"]["planted_change"] is True
    assert synth_nochange.truth()["spec"]["planted_change"] is False
    planted = synth.table("hypothesis_results").get_column("is_headline").any()
    assert (
        planted and not synth_nochange.table("hypothesis_results").get_column("is_headline").any()
    )
