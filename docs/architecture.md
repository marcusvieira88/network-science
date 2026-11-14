# Architecture

How data flows through the pipeline, where the privacy boundary sits, and how the explorer UI is
fed, as implemented. The design began in `specs/001-enron-network-analysis/plan.md` and
`research.md`; table schemas are in `specs/001-enron-network-analysis/contracts/data-contracts.md`
(contract 1.7) and in code in `src/enron_case/contracts/`.

### Data zones and stages

Eleven stages run in order (`src/enron_case/cli.py`, `STAGES`). Each is a function in
`enron_case.<package>.stage`; the zone a stage may touch is decided by its package.

```mermaid
flowchart TB
    subgraph RAW["raw · git-ignored"]
        A[(Corpus archive<br/>sha256 pinned)]
    end
    subgraph ING["ingest · identifiers allowed, purged at end of run"]
        S1[parse<br/>headers only, allowlist]
        S2[clean<br/>normalize + dedupe]
        S3[identity<br/>rules N1–N4, N5 flags custodians]
        T1[(header_records)]
        T2[(messages)]
        T3[(entities + address_map)]
    end
    subgraph RES["restricted · pseudonyms only, git-ignored"]
        S4[pseudo<br/>HMAC, key from outside repo]
        T4[(events + entities_p)]
        S5[network<br/>snapshots, metrics, communities]
        T5[(snapshots, metric_series,<br/>communities)]
        S6[finding<br/>H1–H4, artifact checks, H5–H25,<br/>record profile, H26 departures]
        T6[(hypothesis_results,<br/>artifact_results,<br/>exploratory_results,<br/>profile_results,<br/>departure_results,<br/>departure_test_results)]
        S7[risk<br/>attack R0 with A1 / A2 / A3,<br/>R1 and R2: nothing to match]
        T7[(risk_results)]
        CT[(counts/*.json<br/>counts only)]
    end
    TR[(truth<br/>sample only)]
    CK[(checks/identity_manual.json<br/>committed, counts only)]
    subgraph REL["release · aggregates, k ≥ 5, committed"]
        S8[release<br/>kanon: k-threshold + checks]
        T8[(release/*.csv)]
        S9[report]
        RP[(report.md, run_manifest.json)]
    end
    DOCS[(docs/ decision record,<br/>slides, AI-workflow note)]
    UI[(ui/public/data/release.json)]
    S10[ui-data]
    K{{Key}} -.-> S4
    K -.-> SC
    A --> S1 --> T1 --> S2 --> T2 --> S3 --> T3 --> S4 --> T4
    T4 --> S5 --> T5
    T4 & T5 --> S6 --> T6
    T4 & T5 --> S7 --> T7
    T6 -. headline, for utility .-> S7
    A -. A1 auxiliary data .-> S7
    T3 -. scoring only .-> SC[risk/score.py<br/>counts and rates out] --> S7
    TR -. sample scoring .-> SC
    S1 & S2 & S3 & S4 -. counts .-> CT
    S3 -. manual review .-> CK
    T5 & T6 & T7 & CT & CK --> S8 --> T8 --> S9 --> RP
    S9 --> DOCS
    T8 --> S10 --> UI
```

`counts` is a sub-zone of restricted (`data/restricted/counts/`) holding only the counts side
outputs of each stage (`ingest_counts`, `clean_counts`, `identity_counts`, `pseudo_counts`,
`identity_manual`). `truth` holds the synthetic ground truth and exists only for the sample
corpus. `checks` (`checks/` at the repository root, committed) holds the counts of checks a
person made: `enron-case review-merges` writes `identity_manual.json` there as well as to
`counts`, and the release stage falls back to the committed copy when a run has none, so a fresh
clone publishes the same manual-check rows. `ui` and `docs` are write targets of the last two
stages and can be built only from `release`. `logs` (`data/logs/`, git-ignored) holds run logs,
never data: only the orchestrator writes there, the seconds each stage took
(`stage_timings.json`), which stay out of the committed manifest because they change on every run.

Four mechanisms make the picture enforceable:

1. **Path guard** (`zones.py`). `ALLOWED` maps each package to the zones it may read or write;
   anything else raises `PrivacyViolation` (exit 6). Two documented exceptions in `risk` are
   pinned to single modules by `tests/privacy/test_zones.py`: only `risk/aux_public.py` reads
   the raw archive (the attacker's own copy of the public corpus) and only `risk/score.py`
   reads the ingest zone, the truth and the key (to score guesses, returning counts only).
2. **StageContext** (`context.py`) is the only way a stage reads or writes data: `ctx.read`,
   `ctx.write`, `ctx.write_counts`, `ctx.read_counts`, `ctx.path`. Every table write is
   conformed and validated against its contract, leak-checked (no `@` in restricted; no `@`,
   `p_…` or `o_…` pattern in release: a pattern check, which a bare name would pass) and
   fingerprinted for the run manifest. Only the
   `release` package may write release tables; counts files refuse any `@`.
3. **Import boundary** (`tests/privacy/test_import_boundary.py`). `network`, `finding`, `risk`,
   `release`, `report` and `uiexport` may not import `ingest`, `clean` or `identity`;
   `uiexport` may import only release-side helpers.
4. **One release gate** (`release/kanon.py`). Every release table passes `kanon.enforce`: no
   identifier pattern, no person count below k in any column of
   `schemas.PERSON_COUNT_COLUMNS`, only the default variant in `weekly_metrics`, no core row
   where observed minus core `n_active` would count 1 to k − 1 persons (the core is nested in
   the observed network; the builder suppresses that core row), no lone recoverable cell in
   `degree_distribution`, and no `departures` row whose complement (at risk minus a published
   count) is below k. A violation aborts the run.

The privacy canary (`tests/privacy/test_canary.py`) runs the pipeline on the synthetic corpus,
which carries markers in bodies, subjects, folder names and file names, and checks that none of
those four appears in any zone at all (ingest, restricted, release, ui, docs, logs) or in a log
line. It also checks that no `@`, display name or mailbox owner's folder name reaches the
restricted zone, the release, the UI data, the documents, the manifest or the logs.

### One-command run

```mermaid
sequenceDiagram
    actor Rev as Reviewer
    participant M as make / run.cmd (enron-case all)
    participant P as enron-case
    participant Z as data/, release/, docs/
    participant U as ui/
    Rev->>M: make
    M->>M: prerequisites: uv, Python 3.12, Node ≥ 20, npm, free port 4173
    M->>M: uv sync --locked, npm ci
    M->>P: check-key (a key is created outside the repo if none is configured)
    M->>P: stage fetch: download the archive, verify sha256
    M->>P: run: parse … report
    P->>Z: tables, report.md, documents, run_manifest.json, then the ingest zone is purged (also on failure)
    M->>M: enron-case gate (Python), enron-case ui-gate (UI)
    M->>P: stage ui-data
    P->>U: ui/public/data/release.json
    M->>U: npm run build
    M-->>Rev: report path, held-true summary, then serves http://localhost:4173
```

Each step prints one line and logs to `data/logs/<step>.log`; the first failing step stops the
run with its exit code. `make check` (`uv run enron-case check` on Windows) does everything
except serving. On a fresh clone the whole
run took about 25 minutes (about 20 the download, on that connection); the pipeline itself takes
about 2.5 minutes (the one command prints each step's time, and each run writes the seconds per
stage to `data/logs/stage_timings.json`, which is not committed; the manifest holds no
durations). `enron-case run` purges the ingest zone when it ends, also on failure. A single
`enron-case stage X` keeps it, so the next stage can read it, and prints a warning: finish with
a full `run`, or delete `data/ingest/`, when done.
`enron-case run --sample` (`make sample`) runs the same stages on the synthetic corpus into
`release-sample/` with a fixed test key; documents are written only on real-corpus runs.
`enron-case review-merges` is the manual merge check: it shows a seeded sample of merges in a
terminal and stores only counts (`identity_manual`: `manual_checked`, `manual_correct` and the
same per rule when the review records them; the committed `checks/identity_manual.json` holds
the two totals only).

### Identity resolution and pseudonymization

```mermaid
flowchart LR
    O[Address + name observations<br/>from header_records] --> N1[N1 normalize]
    N1 --> N2[N2 org subdomains]
    N2 --> N3[N3 sender name link<br/>support ≥ 3 + pattern]
    N3 --> N4[N4 legacy directory forms]
    N4 --> G{Guards:<br/>name only? cross-org?<br/>generic local part?<br/>ambiguous legacy?}
    G -- blocked --> X[keep separate, count]
    G -- ok --> U[Union-find cluster<br/>merge tagged with rule]
    U --> TY[Type: person / list / system / role]
    TY --> N5[N5 custodian = mailbox owner]
    N5 --> C[canonical_id = smallest address]
    C --> H[HMAC-SHA256 subkey person-v1]
    H --> P[pseudonym p_…]
    U --> EV[precision / recall vs synthetic truth]
    U --> MC[manual check on real data:<br/>a person judges a seeded sample]
```

Events are emitted per recipient **entity**, so several aliases of one recipient make one event,
not several. Registered domains use a multi-label suffix table (`config.MULTI_LABEL_SUFFIXES`),
so N2 does not merge across companies under `co.uk`-style suffixes.

### Analysis and evidence

```mermaid
flowchart TB
    H0[docs/hypotheses.md<br/>H1–H4 committed first] --> RUN
    E[(events)] --> W[weekly snapshots<br/>core + observed scope]
    W --> MS[metric series<br/>default + sensitivity variants]
    MS --> RUN[H1–H4]
    RUN --> CP[change point + permutation p]
    RUN --> ES[effect size + block bootstrap CI]
    RUN --> NM[null model: recipients shuffled<br/>within week, weights kept]
    RUN --> RB[robustness: leave-one-mailbox-out,<br/>recipient cap, monthly window]
    CP & ES --> HC[Holm correction → supported?]
    NM & RB --> CF[confidence]
    HC --> AC{artifact checks, post hoc<br/>H2 baseline placebo<br/>H3 within custodian}
    AC -- fail or cannot run --> LOW[confidence capped at low,<br/>never headline]
    AC -- pass --> CF
    CF --> HL{supported, confidence high?}
    HL -- yes --> F[headline: largest effect]
    HL -- no --> NS[reported, no headline]
    LOW --> NS
    E --> X[H5–H25: paired within-custodian<br/>crisis vs same weeks a year earlier]
    X --> XP[Wilcoxon p, Holm across 21,<br/>median bootstrap CI]
    X --> XPL[pre-crisis placebo,<br/>leave-one-custodian-out]
    X --> XV[volume-equalised check]
    X --> XR[retention check: H16, H25<br/>custodian-to-custodian only]
    XP & XPL & XV & XR --> XO[confident / inconclusive /<br/>not supported]
    F & NS --> T[(hypotheses, artifact_checks)]
    XO --> T2[(exploratory)]
    E --> PR[record profile: custodians' mail<br/>and after-hours share by month]
    PR --> T3[(record_profile)]
    E --> DP[H26: custodian departures, post hoc<br/>silence while the mailbox still receives]
    DP --> DT[Fisher vs same weeks a year earlier,<br/>placebo, rolling windows, leave-one-out,<br/>variants]
    DT --> T4[(departures, departure_tests)]
```

Three timing labels are used on every surface. H1–H4 are "pre-registered" (before any real
data). H5–H24 are "stated before computed, after earlier results": written in
`docs/hypotheses-exploratory.md` (as E1–E20) after H1–H4 had been run. H25 (E21), a replication
test of the "denser network in the crisis" reported by Diesner & Carley (2005), and H26,
custodian departures, are "post hoc": stated after every other result was known, and before
being computed. They are reported as one list H1–H26 everywhere. In the real-corpus run **no
hypothesis is held true**: H2 and H3 pass the pre-registered rule but fail their artifact checks
(baseline drift; a change in which mailboxes hold mail), H1 and H4 are not supported, and of
H5–H25 none is confident. H16, the strongest lead, is not established once inbox retention is
accounted for and is capped at inconclusive; H20 is inconclusive (its placebo fails); H14, H21
and H22 changed the other way; H25 is not established within custodians.

H26, a structural question stated post hoc (O1 in `docs/hypotheses-exploratory.md`), asks
whether custodians left during the crisis: a departure is a custodian who stops sending for 16
weeks while their own mailbox keeps receiving mail that only it can hold, so a mailbox that was
no longer collected (a record end) does not count. It is **not established**: too few
departures in the crisis window to publish, and not a higher share than a year earlier.

The finding: the record changed (high confidence that it changed; cause not established). No
behavioural finding about the crisis year is claimed. The record profile (`record_profile`)
shows the share of the custodians' weekday sent mail stamped outside working hours dropping from
about half (up to April 2001) to a few percent (from August 2001 on), falling from May 2001,
while the received mail kept per month grows up to about 3.5 times the largest reference month
(about five times October on October). The `Date` convention changed between the windows every
comparison sets against each other, so the report states that change first.

### Re-identification test

```mermaid
flowchart LR
    subgraph Attacker["Attacker side — no access to truth"]
        AUX1[A1: features from public raw corpus<br/>naive parse, per address]
        AUX2[A2: A1 + a few known custodians<br/>as seeds, propagated over contacts]
        AUX3[A3: propagation seeded with<br/>every custodian the corpus names]
        ATT[matching / seed propagation]
    end
    R0[(R0 node-level edges<br/>observed-scope snapshots,<br/>in memory only)] --> ATT
    R1[(R1 = published aggregates, k ≥ 5,<br/>no pseudonyms)] -. no person-level record,<br/>nothing to match .-> ATT
    R2[(R2 = R1 + seeded Laplace noise)] -. nothing to match .-> ATT
    AUX1 --> ATT
    AUX2 --> ATT
    AUX3 --> ATT
    ATT --> GZ[guesses]
    GZ --> SC[risk/score.py<br/>reads ingest or truth, counts only]
    SC --> RT[(risk_results:<br/>uniqueness, re-id rate + CI,<br/>utility per release)]
```

R0, which is never published, is the only release measured. R1 and R2 contain no person-level
records, so the attackers have nothing to match: their rate is 0 by construction, not a
measurement. No group-level attack was built.

### Explorer UI

```mermaid
flowchart LR
    subgraph REL["release (k ≥ 5, no pseudonyms)"]
        T8[(release/*.csv<br/>+ run_manifest.json)]
    end
    T8 --> S10[ui-data stage · uiexport<br/>validates every table, re-checks<br/>identifiers and person counts]
    S10 --> J[(ui/public/data/release.json<br/>the UI's only input)]
    J --> APP[React 18 + TypeScript · Vite<br/>shadcn/ui · dark theme]
    subgraph Views
        V0[Executive summary<br/>landing view: six plain-language cards]
        V1[Overview<br/>plain-language answer, finding statement, key numbers]
        V2["Metrics<br/>metric / scope / variant selectors<br/>(only the default variant is published),<br/>change point, public events, baseline band"]
        V3[Network<br/>plain-language week summary; Sigma.js WebGL<br/>graph of groups, ForceAtlas2, zoom, fullscreen,<br/>search, hover, week slider; group-size dots and<br/>Overlap modes; SVG fallback]
        V4[Clusters<br/>chord diagram of group-to-group weight,<br/>per-group table]
        V5[Hypotheses<br/>plain-language verdicts; one list H1–H26,<br/>artifact and retention checks,<br/>H26 counts, tests and power]
        V6[Data quality<br/>cleaning funnel, header rulings,<br/>manual merge check]
        V7[Privacy and risk<br/>R0 / R1 / R2 by attacker A1–A3]
        V8[Limits]
        V9[Glossary]
    end
    APP --> V0 & V1 & V2 & V3 & V4 & V5 & V6 & V7 & V8 & V9
```

Rules for the UI:

1. It is a static site. Its only input is `release.json`, produced from `release/` alone (the
   release tables except `record_profile`, plus the manifest's run block without
   fingerprints), so it shows nothing that is not in the release. `ui/src/lib/data.ts`
   validates the file at load. The ten views are listed in `ui/src/lib/views.ts`.
2. The network and cluster views draw **groups** (baseline communities with at least k members)
   and the weekly tie weight between them. The Network view draws them with Sigma.js (WebGL)
   through React Sigma and graphology, loaded as a separate chunk when the view opens; positions
   come from one deterministic ForceAtlas2 run over all weeks. It has zoom, fullscreen, search by
   group label and hover highlighting; without WebGL, or if the WebGL view fails, it shows an SVG
   network laid out with `d3-force`. The group-size dots mode draws, inside each group, as many dots as the group has
   persons, at seeded random positions: the dots only show how many people a group has, not real
   individuals or ties; they carry no label, tooltip, hover text, tie or data (Sigma keys are
   opaque sequence numbers). The Overlap mode (WebGL only) draws the week's six
   heaviest group pairs by message count as intersecting outlined contours (one `@sigma/layer-webgl` layer, drawn from group nodes only); an overlap is mail
   between groups, never shared members. The release's `other` bucket (people with no tie in the
   baseline plus communities under k) is not a group: neither view draws or lays it out as one;
   both call it "Outside the 2000 groups" and state the share of mail involving it
   (`ui/src/lib/outside.ts`, docs/metrics.md). There is
   no person-level node, tooltip or table anywhere (`ui/src/privacy.test.ts`).
3. No outside requests: fonts and assets are bundled; no analytics, no CDN.
   `ui/scripts/check-build.mjs` (run by `make ui-gate`) scans the build for external URLs.
4. `make` builds and serves the UI as its last steps (so it needs Node 20+); `make ui` exports
   the data, builds and serves the interface on its own. The UI does not show the month-by-month
   record profile, which is in the report; its Executive summary names the record change through
   H5 and the two comparison windows.
