"""Synthetic organisation and message stream with ground truth.

Mirrors the structure of the real corpus (custodian mailboxes, aliases, duplicates across
folders, Bcc visible only in the sender's copy, noise) at a few thousand messages, so every
stage can be tested against known answers. All names and domains are invented.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from enron_case.config import SAMPLE_INTERNAL_DOMAIN

FIRST = (
    "alex",
    "blake",
    "casey",
    "dana",
    "eli",
    "frances",
    "gale",
    "harper",
    "ira",
    "jordan",
    "kai",
    "lee",
    "morgan",
    "noel",
    "oakley",
    "parker",
    "quinn",
    "reese",
    "sam",
    "taylor",
    "uma",
    "val",
    "wren",
    "xan",
    "yael",
    "zion",
    "avery",
    "bailey",
    "cameron",
    "drew",
)
LAST = (
    "abbot",
    "baird",
    "castell",
    "dorsey",
    "ellery",
    "fenwick",
    "garrow",
    "hollis",
    "ingram",
    "jessop",
    "kendal",
    "lockley",
    "marlow",
    "norcott",
    "oswin",
    "pryce",
    "quarry",
    "radley",
    "sexton",
    "tolland",
    "upton",
    "varley",
    "whitlock",
    "yardley",
    "zeller",
)
EXTERNAL_DOMAINS = ("northgas-partners.com", "brightline-capital.com", "harbor-legal.com")


@dataclass(eq=False)
class Entity:
    truth_id: str
    type: str  # person, list, system, role
    display_name: str
    primary: str
    org_domain: str
    is_internal: bool
    community: int = -1
    is_custodian: bool = False
    owner_dir: str | None = None
    subdomain_alias: str | None = None  # rule N2
    name_alias: str | None = None  # rule N3 (used as sender with the same display name)
    activity: float = 1.0

    @property
    def addresses(self) -> list[str]:
        return [a for a in (self.primary, self.subdomain_alias, self.name_alias) if a]


@dataclass
class Message:
    truth_id: str
    sender: Entity
    sender_addr: str
    to: list[str]
    cc: list[str]
    bcc: list[str]
    ts_utc: datetime | None
    date_header: str
    noise: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class SynthSpec:
    seed: int = 7
    n_internal: int = 56
    n_custodians: int = 12
    n_external: int = 14
    n_communities: int = 4
    start: date = date(2000, 1, 3)
    end: date = date(2002, 3, 25)
    change_week: date = date(2001, 8, 13)
    planted_change: bool = True
    weekly_rate: float = 0.35
    domain: str = SAMPLE_INTERNAL_DOMAIN
    n_hubs: int = 3


@dataclass
class Organisation:
    persons: list[Entity]
    custodians: list[Entity]
    externals: list[Entity]
    lists: list[Entity]
    system: Entity
    role: Entity
    hubs: list[Entity]

    @property
    def everyone(self) -> list[Entity]:
        return [*self.persons, *self.externals, *self.lists, self.system, self.role]


def build_organisation(spec: SynthSpec, rng: random.Random) -> Organisation:
    names = [(f, la) for la in LAST for f in FIRST]
    rng.shuffle(names)
    persons: list[Entity] = []
    for i in range(spec.n_internal):
        first, last = names[i]
        persons.append(
            Entity(
                truth_id=f"P{i:03d}",
                type="person",
                display_name=f"{first.title()} {last.title()}",
                primary=f"{first}.{last}@{spec.domain}",
                org_domain=spec.domain,
                is_internal=True,
                community=i % spec.n_communities,
            )
        )
    for i, person in enumerate(persons):
        if i % 4 == 1:
            person.subdomain_alias = person.primary.replace("@", "@ect.")
        if i % 7 == 2:
            first, last = person.primary.split("@")[0].split(".")
            person.name_alias = f"{first[0]}{last}@{spec.domain}"
    custodians = persons[: spec.n_custodians]
    for person in custodians:
        first, last = person.primary.split("@")[0].split(".")
        person.is_custodian = True
        person.owner_dir = f"{last}-{first[0]}"
        person.activity = 3.0
    hubs = [p for p in custodians if p.community == 0][: spec.n_hubs]

    externals: list[Entity] = []
    for i in range(spec.n_external):
        first, last = names[spec.n_internal + i]
        domain = EXTERNAL_DOMAINS[i % len(EXTERNAL_DOMAINS)]
        externals.append(
            Entity(
                truth_id=f"X{i:03d}",
                type="person",
                display_name=f"{first.title()} {last.title()}",
                primary=f"{first}.{last}@{domain}",
                org_domain=domain,
                is_internal=False,
                activity=0.4,
            )
        )
    # Homonym: an external person with the same name and local part as an internal person.
    twin = persons[spec.n_custodians + 1]
    externals.append(
        Entity(
            truth_id="X900",
            type="person",
            display_name=twin.display_name,
            primary=twin.primary.split("@")[0] + "@" + EXTERNAL_DOMAINS[0],
            org_domain=EXTERNAL_DOMAINS[0],
            is_internal=False,
            activity=0.6,
        )
    )
    lists = [
        Entity("L000", "list", "All Traders", f"all.traders@{spec.domain}", spec.domain, True),
        Entity("L001", "list", "Risk Desk", f"risk.desk@{spec.domain}", spec.domain, True),
    ]
    system = Entity(
        "S000", "system", "Mailer Daemon", f"mailer-daemon@{spec.domain}", spec.domain, True
    )
    role = Entity(
        "R000", "role", "Announcements", f"announcements@{spec.domain}", spec.domain, True
    )
    return Organisation(persons, custodians, externals, lists, system, role, hubs)


def date_header(local: datetime) -> tuple[str, datetime]:
    """Render a Pacific-time Date header and return it with the UTC instant."""
    summer = 4 <= local.month <= 10
    offset, label = (-7, "PDT") if summer else (-8, "PST")
    utc = (local - timedelta(hours=offset)).replace(tzinfo=UTC)
    header = local.strftime("%a, %d %b %Y %H:%M:%S ") + f"{offset:+03d}00 ({label})"
    return header, utc


def generate_messages(spec: SynthSpec, org: Organisation, rng: random.Random) -> list[Message]:
    messages: list[Message] = []
    senders = [*org.persons, *org.externals]
    week = spec.start
    counter = 0
    while week <= spec.end:
        after = spec.planted_change and week >= spec.change_week
        for sender in senders:
            n = _poisson(rng, spec.weekly_rate * sender.activity)
            for _ in range(n):
                msg = _person_message(spec, org, rng, sender, week, after, f"M{counter:06d}")
                counter += 1
                if msg is not None:
                    messages.append(msg)
        if (week - spec.start).days % 42 == 0:
            messages.append(_mass_mailing(org, rng, week, f"M{counter:06d}"))
            counter += 1
        if rng.random() < 0.3:
            target = rng.choice(org.custodians)
            local = _local_time(rng, week)
            header, utc = date_header(local)
            messages.append(
                Message(
                    f"M{counter:06d}",
                    org.system,
                    org.system.primary,
                    [target.primary],
                    [],
                    [],
                    utc,
                    header,
                )
            )
            counter += 1
        week += timedelta(days=7)
    return messages


def _person_message(
    spec: SynthSpec,
    org: Organisation,
    rng: random.Random,
    sender: Entity,
    week: date,
    after: bool,
    truth_id: str,
) -> Message | None:
    cross_p = 0.45 if after else 0.12
    hub_p = 0.55 if after else 0.05
    k = min(1 + _geometric(rng, 0.55), 7)
    recipients: list[Entity] = []
    for _ in range(k):
        roll = rng.random()
        if roll < 0.12:
            pool = org.externals
        elif sender.is_internal and roll < 0.12 + cross_p:
            pool = [p for p in org.persons if p.community != sender.community]
        else:
            community = (
                sender.community if sender.is_internal else rng.randrange(spec.n_communities)
            )
            pool = [p for p in org.persons if p.community == community]
        weights = [2.5 if p.is_custodian else 1.0 for p in pool]
        recipients.append(rng.choices(pool, weights=weights)[0])
    if sender.is_internal and rng.random() < hub_p:
        recipients[0] = rng.choice(org.hubs)
    if rng.random() < 0.03:
        recipients.append(rng.choice(org.lists))
    recipients = [r for r in dict.fromkeys(recipients) if r is not sender]
    if not recipients and rng.random() > 0.3:
        return None

    observable = sender.is_custodian or any(r.is_custodian for r in recipients)
    if not observable:
        return None

    sender_addr = sender.primary
    if sender.name_alias and rng.random() < 0.35:
        sender_addr = sender.name_alias
    elif sender.subdomain_alias and rng.random() < 0.25:
        sender_addr = sender.subdomain_alias

    addrs = [_recipient_addr(rng, r) for r in recipients]
    split = max(1, len(addrs) - rng.randrange(0, 3))
    to, cc = addrs[:split], addrs[split:]
    bcc: list[str] = []
    noise: set[str] = set()
    if rng.random() < 0.05:
        bcc = [_recipient_addr(rng, rng.choice(org.persons))]
        bcc = [a for a in bcc if a not in to and a not in cc]
    if cc and rng.random() < 0.03:
        to.append(cc[0])  # same recipient in two fields
        noise.add("dup_role")

    local = _local_time(rng, week)
    header, utc = date_header(local)
    ts: datetime | None = utc
    roll = rng.random()
    if roll < 0.004:
        local = local.replace(year=1980)
        header, ts = date_header(local)
        noise.add("date_out_of_range")
    elif roll < 0.008:
        header, ts = "unknown date", None
        noise.add("bad_date")
    elif roll < 0.013:
        to, cc, bcc = [sender_addr], [], []
        noise.add("self_only")
    elif roll < 0.016:
        to, cc, bcc = [], [], []
        noise.add("no_recipients")
    elif roll < 0.026:
        to.append("undisclosed-recipients:;")
        noise.add("bad_address")
    if rng.random() < 0.04 and to and "@" in to[0]:
        local_part, domain = to[0].split("@")
        to[0] = f"{local_part.title()}@{domain}"  # case variant (rule N1)
    return Message(truth_id, sender, sender_addr, to, cc, bcc, ts, header, noise)


def _mass_mailing(org: Organisation, rng: random.Random, week: date, truth_id: str) -> Message:
    local = _local_time(rng, week)
    header, utc = date_header(local)
    to = [p.primary for p in org.persons]
    return Message(truth_id, org.role, org.role.primary, to, [], [], utc, header, {"mass_mailing"})


def _recipient_addr(rng: random.Random, entity: Entity) -> str:
    if entity.subdomain_alias and rng.random() < 0.3:
        return entity.subdomain_alias
    return entity.primary


def _local_time(rng: random.Random, week: date) -> datetime:
    day = week + timedelta(days=rng.randrange(5))
    return datetime(day.year, day.month, day.day, rng.randrange(7, 20), rng.randrange(60), 0)


def _poisson(rng: random.Random, lam: float) -> int:
    count, total = 0, rng.expovariate(1.0)
    while total < lam:
        count += 1
        total += rng.expovariate(1.0)
    return count


def _geometric(rng: random.Random, p: float) -> int:
    n = 0
    while rng.random() > p:
        n += 1
    return n
