"""Render synthetic messages as maildir files (one per stored copy) and write the tar archive.

Layout and header order follow the public corpus: maildir/<owner>/<folder>/<n>.
Every copy carries canary markers in places the pipeline must never read or keep.
"""

from __future__ import annotations

import gzip
import io
import random
import tarfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from enron_case.synth.model import Entity, Message, Organisation

FOLD_AT = 78
CANARY_FOLDER = "canaryfolder_projects"


@dataclass
class FileRecord:
    member_path: str
    owner: Entity
    folder: str
    message: Message
    is_sender_copy: bool
    message_id: str
    folded: bool
    to: list[str]
    cc: list[str]
    bcc: list[str]
    x_to: str | None
    x_cc: str | None
    x_bcc: str | None
    text: str = field(repr=False, default="")


def build_files(org: Organisation, messages: list[Message], rng: random.Random) -> list[FileRecord]:
    by_addr = {a.lower(): e for e in org.everyone for a in e.addresses}
    counters: dict[tuple[str, str], int] = {}
    files: list[FileRecord] = []
    for msg in messages:
        for owner, folder, sender_copy in _copies(msg, by_addr, rng):
            assert owner.owner_dir is not None
            key = (owner.owner_dir, folder)
            counters[key] = counters.get(key, 0) + 1
            path = f"maildir/{owner.owner_dir}/{folder}/{counters[key]}."
            files.append(_render(path, owner, folder, msg, sender_copy, by_addr, rng))
    return files


def _copies(
    msg: Message, by_addr: dict[str, Entity], rng: random.Random
) -> list[tuple[Entity, str, bool]]:
    out: list[tuple[Entity, str, bool]] = []
    if msg.sender.is_custodian:
        out.append((msg.sender, "_sent_mail", True))
        if rng.random() < 0.6:
            out.append((msg.sender, "sent", True))
        if rng.random() < 0.4:
            out.append((msg.sender, "all_documents", True))
    seen: set[str] = set()
    for addr in [*msg.to, *msg.cc, *msg.bcc]:
        entity = by_addr.get(addr.lower())
        if entity is None or not entity.is_custodian or entity is msg.sender:
            continue
        if entity.truth_id in seen:
            continue
        seen.add(entity.truth_id)
        out.append((entity, "inbox", False))
        if rng.random() < 0.15:
            out.append((entity, "deleted_items", False))
        if rng.random() < 0.25:
            out.append((entity, "all_documents", False))
        if rng.random() < 0.03:
            out.append((entity, CANARY_FOLDER, False))
    return out


def _render(
    path: str,
    owner: Entity,
    folder: str,
    msg: Message,
    sender_copy: bool,
    by_addr: dict[str, Entity],
    rng: random.Random,
) -> FileRecord:
    bcc = list(msg.bcc) if sender_copy else []
    message_id = (
        f"<{rng.randrange(10**7, 10**8)}.{rng.randrange(10**12, 10**13)}.JavaMail.evans@thyme>"
    )
    marker = f"{rng.getrandbits(48):012x}"
    folded = False
    lines = [f"Message-ID: {message_id}", f"Date: {msg.date_header}", f"From: {msg.sender_addr}"]
    for name, addrs in (("To", msg.to), ("Cc", msg.cc), ("Bcc", bcc)):
        if addrs:
            line, was_folded = _address_line(name, addrs)
            lines.append(line)
            folded = folded or was_folded
    lines += [
        f"Subject: Re: CANARYSUBJ{marker} quarterly numbers",
        "Mime-Version: 1.0",
        "Content-Type: text/plain; charset=us-ascii",
        "Content-Transfer-Encoding: 7bit",
        f"X-From: {msg.sender.display_name}",
    ]
    x_values: dict[str, str | None] = {}
    for name, addrs in (("X-To", msg.to), ("X-cc", msg.cc), ("X-bcc", bcc)):
        names = [_display(a, by_addr) for a in addrs]
        value = ", ".join(names) if names else None
        x_values[name] = value
        if value is None:
            lines.append(f"{name}: ")
        else:
            line, was_folded = _address_line(name, names)
            lines.append(line)
            folded = folded or was_folded
    assert owner.owner_dir is not None
    label = f"CANARYFOLDER{marker}" if folder == CANARY_FOLDER else folder.replace("_", " ").title()
    stamp = (msg.ts_utc or datetime(2001, 1, 1)).strftime("%b%Y")
    lines += [
        f"X-Folder: \\{owner.display_name.replace(' ', '_')}_{stamp}\\Notes Folders\\{label}",
        f"X-Origin: {owner.owner_dir.title()}",
        f"X-FileName: {owner.owner_dir.replace('-', '')} CANARYFILE{marker} (Non-Privileged).pst",
    ]
    body = f"\nCANARYBODY{marker} please see the attached numbers.\n\nRegards\n"
    text = "\n".join(lines) + "\n" + body
    return FileRecord(
        member_path=path,
        owner=owner,
        folder=folder,
        message=msg,
        is_sender_copy=sender_copy,
        message_id=message_id,
        folded=folded,
        to=list(msg.to),
        cc=list(msg.cc),
        bcc=bcc,
        x_to=x_values["X-To"],
        x_cc=x_values["X-cc"],
        x_bcc=x_values["X-bcc"],
        text=text,
    )


def _address_line(name: str, items: list[str]) -> tuple[str, bool]:
    """Join with ', ' and fold onto continuation lines (',\\n\\t') when the line is long.

    Unfolding (drop the line break, collapse the continuation whitespace to one space)
    restores the ', '-joined value exactly.
    """
    line = f"{name}: " + ", ".join(items)
    if len(line) <= FOLD_AT:
        return line, False
    return f"{name}: " + ",\n\t".join(items), True


def _display(addr: str, by_addr: dict[str, Entity]) -> str:
    entity = by_addr.get(addr.lower())
    return entity.display_name if entity else addr


def write_archive(files: list[FileRecord], target: Path) -> None:
    """Deterministic gzip tar: fixed mtimes, owners and member order."""
    target.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for record in sorted(files, key=lambda f: f.member_path):
            data = record.text.encode("latin-1")
            info = tarfile.TarInfo(record.member_path)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    with target.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        gz.write(buffer.getvalue())
