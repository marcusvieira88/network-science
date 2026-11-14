# Phase 0 Research: Enron Headers-Only Network Analysis Case

Each entry: the decision, why, and what was rejected. Items marked **VERIFY** are expectations
about the corpus from prior knowledge that the ingest work must confirm with counts before the
design relies on them; they were not checked while writing this plan.

## R1. Where "content" ends

**Decision**: Strict reading. The parser reads each message line by line and stops at the first
blank line. Of the header fields, only `Date`, `From`, `To`, `Cc`, `Bcc` yield stored values.
`Subject` is content and its value is never retained. The full field-by-field ruling is in
[contracts/header-allowlist.md](contracts/header-allowlist.md).

**Rationale**: The brief asks us to draw the line deliberately. A subject line is a one-line
summary of the body written by the author; folder names are topic labels written by the owner.
Both are content in everything but position.

**Alternatives considered**:
- *Keyed hash of the normalized subject, used only for deduplication and thread linking.* Better
  dedupe and reply detection, but a hash of a short guessable string is a content fingerprint, and
  it puts content-derived data in the system. Rejected; the lost precision is measured instead.
- *Keep a reply/forward flag derived from the subject prefix.* Small leak, small value. Rejected.

**Cost we accept**: no thread reconstruction, no reply-time metrics, slightly weaker dedupe.

## R2. Reading headers without touching bodies

**Decision**: Stream the archive (`tarfile` in streaming mode), and for each member read lines
until the first blank line, then skip the rest of the member unread. Nothing is extracted to disk.
Headers are decoded as Latin-1 (lossless for any byte) and folded lines are unfolded by hand.

**Rationale**: The standard email parser reads the whole message. A reader that structurally
cannot reach the body is easier to trust and to test than one that parses it and discards it.

**Honest limit**: body bytes still pass through the decompressor on their way to being skipped,
and the downloaded archive on disk contains them. "Never enters the system" means never decoded,
parsed, held, stored or logged by our code. With real customer data the equivalent control is a
connector that requests metadata fields only where the provider offers such a scope, so bodies
and attachments never leave the source; `Subject` still arrives and is discarded at the
allowlist. Chat APIs without such a scope (Teams, Slack) return text, which the connector must
drop in memory.

**Alternatives considered**: extract then parse (content on disk in the clear; rejected);
`email.parser.HeaderParser` (reads the body as payload; rejected).

## R3. Deduplication without content

**Decision**: Two-pass, deterministic.
1. Exact key: normalized sender address + timestamp to the second (UTC) + sorted set of
   normalized recipient addresses.
2. Subset rule: same sender and second, and one recipient set contains the other → merge, keep
   the union (covers the sender's copy holding Bcc recipients the receivers' copies lack).

Each merge records its rule. Precision/recall are measured on the synthetic corpus, where true
duplicates are known, and both rules are reported separately.

**Rationale**: **VERIFY** — in this corpus the `Message-ID` is expected to have been generated at
collection time per stored file, so copies of one message in different folders carry different
IDs and the ID cannot be the dedupe key. Ingest must report the share of exact-key duplicate
groups that share a Message-ID; if the expectation is wrong, Message-ID becomes pass zero.

**Known errors**: distinct messages from one sender to identical recipients in the same second
merge (for a who-talks-to-whom network this costs one unit of tie weight); copies with clock
differences do not merge. Sensitivity of the finding to the dedupe rule is part of FR-017.

**Alternatives considered**: Message-ID only (expected not to work); subject hash (see R1).

## R4. Identity resolution

**Decision**: Rule-based, conservative, recorded. Union-find over normalized addresses with merge
rules applied in order, each merge tagged with the rule that caused it:

| Rule | Evidence | Merges |
|------|----------|--------|
| N1 normalize | case, quotes, stray punctuation, `mailto:` | spelling variants of one address |
| N2 org subdomains | same local part under subdomains of one registered domain | `x@sub.org` and `x@org` |
| N3 sender name link | two addresses used as sender with the same normalized display name, each ≥ 3 times, and compatible local-part pattern | alias addresses of one sender |
| N4 legacy directory form | non-address directory strings paired with an address in the same header position ≥ 3 times | legacy internal forms to addresses |
| N5 mailbox owner | dominant sender address in a mailbox's sent folders | owner flag (`is_custodian`), no merge by itself |

Guards: never merge on name alone; never merge across unrelated external organizations; generic
local parts (`info`, `admin`, …) are excluded from N2/N3. Entities are typed
person / list / system / role / unknown by documented patterns and behaviour (sends to very many,
never sends, placeholder addresses); non-persons are counted but kept out of the person network.

**Rationale**: A false merge invents ties and a central node that does not exist; a false split
only dilutes one. So precision is weighted over recall, every merge is explainable, and the
result is deterministic — which pseudonym stability (R5) needs.

**Evaluation**: synthetic ground truth (precision/recall), plus a 50-merge manual sample on the
real corpus reviewed inside the ingest zone, of which only the counts leave it.

**Alternatives considered**: probabilistic record linkage / embeddings (more recall, not
explainable, not deterministic, no time); a published alias list for the custodians (good recall
for 150 people, but imports an external identity table we cannot audit; kept as an optional
cross-check, not as the method).

## R5. Pseudonymization scheme

**Decision**: `pseudonym = prefix + base32(HMAC-SHA256(subkey, canonical_id))[:16]`.
- `canonical_id`: for a person or other entity, the lexicographically smallest normalized address
  in its resolved cluster; for an organization, its registered domain.
- Subkeys are derived from one master key by label (`person-v1`, `org-v1`, `event-v1`), so a
  person pseudonym and an organization pseudonym can never be compared.
- 80 bits kept; the run asserts there are no collisions.
- Master key: 32 random bytes from the environment or a key file outside the repository. The run
  refuses to start without one or if the key file lies inside the repository.
- Each release re-keys pseudonyms with a per-release salt, so two releases cannot be joined.

**Rationale**: Stable across runs (same key, same input → same output). Irreversible without the
key and, unlike a plain or salted hash, not confirmable by hashing candidate addresses — which
matters because email addresses are a small, guessable space. Consistent with identity resolution
because the hash input is the resolved entity, not the address.

**Honest limits**: whoever holds the key can test any candidate, so this is pseudonymization in
the GDPR sense and the output remains personal data. If identity resolution changes a cluster's
smallest address, that pseudonym changes; a production system needs a persisted entity registry
with surrogate IDs, held with the key on the customer side.

**Alternatives considered**: random IDs with a stored mapping table (stable only while the table
exists; the table is the thing an attacker wants; rejected); unkeyed hash (dictionary attack in
minutes; rejected); format-preserving encryption (reversible by design; not needed).

## R6. Data zones and minimization

**Decision**: Three zones, enforced by path guards and an import-boundary test.

| Zone | Holds | Who may read | Lifetime |
|------|-------|--------------|----------|
| `data/raw`, `data/ingest` | archive; parsed headers with identifiers; address→entity map | ingest, clean, identity, pseudo, risk *scorer* | purged at end of run by default |
| `data/restricted` | pseudonymized events (hour resolution), entity table | network, finding, risk, release | git-ignored |
| `release/` | aggregates meeting minimum group size k=5 | report, docs, reviewers | committed |

Timestamps are truncated to the hour at the boundary; published series are weekly.

**Rationale**: makes Principle II checkable: a module's allowed zones are a property of its
package, tested by reading imports, not a promise.

## R7. Storage and tooling

**Decision**: Python 3.12; `uv` with a lockfile; Polars + Parquet for staged tables; NetworkX,
NumPy, SciPy for networks and statistics; standard-library `argparse`, `hmac`, `tarfile`;
`pytest` + `hypothesis`; `ruff`, `mypy`; GitHub Actions running the gates on the synthetic sample;
`make all` as the one command. Slides are Marp-compatible Markdown that also reads fine unrendered.

**Rationale**: file-based, no services, quick to install. The observed network is in the tens of
thousands of nodes and the custodian core in the low hundreds, well within NetworkX.

**Alternatives considered**: DuckDB (fine, but one dataframe library is enough); pandas (slower,
weaker typing of list columns); igraph (faster, extra native dependency not needed at this size);
a workflow engine such as DVC/Snakemake (reproducibility we get from a 100-line manifest).

## R8. Reproducibility mechanics

**Decision**: every stage writes its table sorted by a declared key and records in
`run_manifest.json` the input fingerprints, parameters, seed, code version and output fingerprint
(SHA-256 over a canonical row serialization, not over Parquet bytes). A stage is skipped when its
inputs and parameters are unchanged. The corpus archive is verified against a pinned SHA-256.

**Rationale**: Parquet bytes can differ across library versions while content is identical;
hashing content makes "identical outputs" (SC-003) a fair test.

## R9. Network construction and metrics

**Decision**: weekly directed weighted snapshots (ISO weeks), with monthly as a sensitivity
variant. Tie weight for a message with n recipients is 1/n per recipient, so mass mailings do not
dominate; messages above a recipient cap (default 50) are excluded from ties and counted.
Two scopes: the **core** (both ends are mailbox owners) and the **observed** network (all
resolved internal persons). Headline results use the core; the observed network is a sensitivity
check.

Metrics, each defined in `docs/metrics.md` before coding: volume, active persons, density,
reciprocity, in-degree concentration (Gini), share of weight crossing baseline communities, share
of weight to external organizations, week-over-week tie turnover (1 − Jaccard).

**Rationale**: a tie is only visible if one end is among about 150 collected mailboxes, so the
observed network is a union of ego networks. The core is the only part observed from both sides.

## R10. Hypotheses, written before results

**Decision**: four hypotheses about 2001, fixed in `docs/hypotheses.md` and committed before the
analysis is run on the real corpus:

| ID | Claim | Metric |
|----|-------|--------|
| H1 | Communication concentrated on fewer people as the crisis approached | in-degree Gini (core) |
| H2 | Communication increasingly crossed established group boundaries | cross-community weight share, communities frozen on a 2000 baseline |
| H3 | The organization turned inward | external share of weight |
| H4 | Working relationships were rewired faster | weekly tie turnover |

The headline finding is the supported hypothesis with the largest effect that passes every
robustness check; all four outcomes are published, and "none supported" is an acceptable result.
Public event dates (CEO resignation in August, the October loss announcement, the December
filing) are used only to annotate the series, not to choose windows.

**Rationale**: the answer to "what did the network know before" is a claim about lead time, which
is exactly where hindsight bias enters. Fixing the hypotheses and reporting the failures is the
defence available in the time.

**As built**: H1–H4 as above, plus H5–H24 (two families stated before each was computed) and
H25, a post-hoc replication test of a published denser-network result (Diesner & Carley,
2005), and H26, a post-hoc structural question about custodian departures, all as one list
H1–H26 (`docs/hypotheses.md`, `docs/hypotheses-exploratory.md`). None is held true. The
finding is descriptive: the record changed from May 2001 on (`record_profile`); no behavioural
finding about the crisis year is claimed.

## R11. Evidence and confidence

**Decision**: for each metric series: (a) change point by a CUSUM statistic with a permutation
p-value; (b) effect size as the standardized difference between the baseline period and the
post-change period, with a moving-block bootstrap interval; (c) a null model that rewires
recipients within each week preserving every sender's out-volume and every recipient's in-volume,
to separate structural change from volume change; (d) leave-one-mailbox-out re-estimation; (e)
re-estimation across recipient cap and window length (dedupe-rule variant dropped for time; see docs/ai-workflow-log.md); (f) Holm correction across the
four hypotheses. Confidence is stated in words (high / moderate / low) by a rule written in
`docs/metrics.md`: high requires passing (a)–(f).

**Rationale**: implements Principle IV and V with methods small enough to write and test from
scratch on synthetic series with a planted change.

**Known threats, to be stated next to the result**: mailbox retention differs by person and
period, so volume and coverage rise toward late 2001 for reasons unrelated to behaviour; the
sample is senior staff; the collection was shaped by an investigation.

## R12. Re-identification: attacker models and tests

**Decision**: two attackers, three releases, one table.

- **A1, outsider with the public corpus**: computes per-address features from the raw corpus with
  a naive parser of their own (weekly send/receive counts, degree) and matches them to what a
  release exposes.
- **A2, insider with partial knowledge**: knows a few true identities ("seeds") and their
  contacts, and propagates from them through the pseudonymized graph.
- **Releases**: R0 pseudonymized node-level weekly edge list (the naive output); R1 aggregates
  only with minimum group size 5, bucketed degree distributions, weekly resolution, per-release
  re-keying; R2 as R1 with calibrated noise added to counts.

Measures: share of persons unique on each attacker-observable feature and the distribution of
anonymity-set sizes; top-1 re-identification rate of each attack; and for each release the loss
of analytical value, measured as the change in the headline effect and its interval.

The attack code receives only a release and auxiliary knowledge. Scoring against the truth is a
separate function that reads the address→entity map inside the ingest zone and emits counts only.

**Expected result, to be confirmed**: against R0, A1 re-identifies nearly every active person,
because timestamps and degree sequences are near-unique fingerprints and the attacker holds the
original. This is the main point of the section: pseudonymized node-level communication data
stays personal data and does not leave the restricted zone. R1 and R2 should leave A1 with
nothing at person level to match, and the finding should survive.

**Alternatives considered**: reporting only k-anonymity of degree (measures uniqueness, not an
attack); differential privacy with a formal budget across all outputs (right direction for the
product, too much to do correctly in the time; R2 is presented as a sketch with that caveat).

**As built**: three attackers. A3, added in the final review, is the A2 propagation seeded with
every custodian: the public corpus names every mailbox owner, so anyone holding it knows them
all. R1 carries no pseudonyms, so per-release re-keying was dropped; R2's noise has a fixed scale
and is not calibrated to a budget. On R0, A1 re-identified about a quarter of the targets and A2
and A3 more than half, not nearly everyone; on R1 and R2 the rate is 0 by construction, not a
measurement: no person-level record remains to match. No group-level
attack on `community_graph` was run (`release/report.md`, limits).

## R13. Keeping agent-written code correct

**Decision**: five mechanisms, all in the repository.
1. Contracts first: table schemas and the CLI are fixed before parallel work begins.
2. Ground truth first: the synthetic corpus generator and the contract fixtures exist before the
   modules, so each agent's tests are written against answers it did not produce.
3. Gates: `make gate` = lint, types, unit and contract tests, privacy canary, import-boundary
   test. No merge without a green gate.
4. Independent review: each work package is reviewed by an agent that did not write it, using
   the `/code-review` skill and the project's own `/data-privacy-review` skill, which checks the
   content promise first; the lead integrates and runs the
   full corpus.
5. Security review: the `/security-review` skill is run on the whole repository before
   submission, with key handling, zone boundaries and what is committed as the focus.

A running log (`docs/ai-workflow-log.md`) records per package what was delegated, what was
rejected and why. The AI-workflow note is distilled from it.

**Rationale**: an engineering system where agents write most of the code needs these checks to
stay correct, and the log is the
evidence for the AI-workflow deliverable.

## R14. Explorer UI

**Decision**: an optional static web interface in `ui/`: React + TypeScript + Vite, shadcn/ui on
Tailwind in a dark theme, shadcn charts (Recharts) for time series and `d3-force` for the network
view. It reads one JSON file exported from `release/` and nothing else. The network view shows
baseline communities of at least k persons as nodes and weekly tie weight between them as edges.

**Rationale**: a week-by-week picture of how groups connect is the most direct way to show an
organizational change to an audience, and it is the one thing a table does poorly. Building it on
the release keeps it under the same guarantees as the report: it cannot show a person, because
the data it is given contains none.

**Privacy consequence**: `community_graph.csv` is a new published table, so it is part of release
R1 and is attacked like the rest (research R12). Group membership itself is never published; only
group sizes and group-to-group weights are. If the attack shows that the group graph helps
re-identification, the table is coarsened (fewer, larger groups; monthly instead of weekly) or
dropped, and the UI falls back to charts only.

**Alternatives considered**: a person-level interactive graph (needs pseudonymized node-level
data outside the restricted zone, which the risk analysis is expected to show is re-identifiable;
rejected); a single generated HTML page with charts (simpler, no second toolchain; this was the
first proposal and remains the fallback if the UI is cut); a notebook (not reproducible as a
deliverable, mixes code and output).

**Cost**: a second toolchain (Node), one more work package and agent, and UI tests. Kept out of
`make all` so the brief's one-command requirement does not depend on it.

**As built**: the UI became part of the one command (`make` builds it, runs its gate and serves
it; Node 20+ is a prerequisite). The network view is drawn with React Sigma + Sigma.js over
graphology, laid out once with ForceAtlas2, with an SVG `d3-force` fallback without WebGL; a
Clusters view (chord diagram), an Executive summary landing view and a Glossary were added,
ten views in all. The group graph was not attacked (see R12).
