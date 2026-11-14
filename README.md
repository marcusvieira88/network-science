# Headers-only network analysis of the Enron email corpus

An engineering case study: a privacy-first pipeline that reads only the headers of the public Enron
email corpus, so message content never enters the system. It cleans and pseudonymizes the headers,
tests pre-stated hypotheses about how the communication network changed in the 2001 crisis,
attacks its own output to measure re-identification risk, and publishes only aggregates.

## Run it

Prerequisites: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 20+, `make`.

```bash
make          # `make check` does the same without serving the explorer
```

It installs locked dependencies, creates a key outside the repository if needed, fetches and
verifies the corpus, runs the pipeline and every test, then serves the explorer at
http://localhost:4173. A fresh clone took about 24 minutes, 20
of them the download; the pipeline itself takes about 2.5.

## Results in brief

- **Content line:** `Subject` and folder names count as content and are dropped as each line is
  read; only `Date` and the address fields are used, and addresses never leave the ingest zone.
- **Data quality:** about 517,000 files, half of them duplicate copies, give about 250,000
  messages; about 85,400 addresses resolve to about 84,800 entities.
- **Finding:** what changed in the crisis year is the *record*, not measurable behaviour. For
  the same custodians, the share of weekday sent mail stamped outside working hours drops from
  about half to a few percent between spring and late summer 2001, and the received mail kept
  per month grows up to several-fold: the `Date` convention changed (most likely the mail system)
  right between the windows every comparison sets against each other. Confidence: high that the
  record changed; its cause is not established.
- **Behaviour:** no hypothesis among H1–H25 is held true. H2/H3 passed their tests but are
  artifacts (stale baseline groups; a changing mailbox mix); H16 fails its retention check; H25,
  a post-hoc replication of the published "denser network in the crisis", finds no change within
  custodians.
- **Risk:** person-level pseudonymized edges are re-identifiable: an outsider (A1) matches about
  a quarter of people, an insider knowing a few custodians (A2) more than half, one knowing all of
  them (A3; the corpus names them) about as many. So only aggregates are published, every group
  at least five people, leaving no person-level record to match.

## Architecture and data flow

Data lives in zones. A path guard (`zones.py`) confines each package to the zones it may use, and
an import-boundary test keeps everything after `pseudo` away from the identifier-side packages. The
ingest zone is deleted at the end of every run; `risk` alone may score its guesses against it,
emitting counts only.

```mermaid
flowchart LR
    KEY{{"key: ~/.config/enron-case/key<br/>outside the repo"}}
    subgraph RAW["raw · git-ignored"]
        A[("CMU archive")]
    end
    subgraph ING["ingest · addresses and names, purged at end of run"]
        ingest --> clean --> identity
    end
    GUARD{{"privacy boundary<br/>path guard + import-boundary test"}}
    subgraph RES["restricted · pseudonyms only, git-ignored"]
        pseudo --> network --> finding
        network --> risk
        CNT[("counts<br/>per-stage counts")]
    end
    CHK[("checks<br/>manual merge counts")]
    subgraph REL["release · aggregates, k ≥ 5, committed"]
        release
    end
    DOCS[("docs<br/>report.md, documents")]
    UI[("ui<br/>release.json")]
    A --> ingest
    identity -.-> CHK
    identity --> GUARD --> pseudo
    KEY -.-> pseudo
    finding & risk --> release
    CHK -.-> release
    release -->|report| DOCS
    release -->|uiexport| UI
```

Each arrow names what crosses it; every table crossing a zone is validated against a contract.

```mermaid
flowchart TB
    D["CMU tarball<br/>download + SHA-256 check<br/>make, scripts/run-all.sh"]
    H["ingest: read each header<br/>stop at the first blank line<br/>Subject, body, attachments never read"]
    C["clean: normalize, dedupe"]
    I["identity: resolve aliases, rules N1–N5"]
    P["pseudo: keyed HMAC<br/>p_ person, o_ org, e_ event, m_ message"]
    N["network: weekly snapshots,<br/>Louvain groups"]
    F["finding: H1–H25,<br/>record profile"]
    R["risk: attackers A1–A3"]
    K["release: suppress groups under 5"]
    T[("release/*.csv + report.md")]
    U["uiexport"]
    J[("ui/public/data/release.json")]
    V["Vite + React explorer: Overview · Metrics · Network · Clusters<br/>Hypotheses · Data quality · Privacy and risk · Limits"]
    D -->|"archive bytes"| H
    H -->|"header records with addresses:<br/>Date, From, To, Cc, Bcc, X-From,<br/>X-To, X-cc, X-bcc, Message-ID"| C
    C -->|"deduplicated messages"| I
    I -->|"entities + address map"| P
    P -->|"pseudonymized events"| N
    N -->|"snapshots, metrics, groups"| F
    N -->|"snapshots"| R
    F -->|"results"| K
    R -->|"risk scores"| K
    K -->|"aggregates ≥ 5"| T
    T -->|"release tables only"| U
    U -->|"one JSON file"| J
    J -->|"fetched by the browser"| V
```

## Decision record

| Trade-off | Gained | Paid |
|-----------|--------|------|
| Strict content line, including `Subject` | no content fingerprint, not even hashed | no threads or reply times; dedupe without content |
| Rule-based identity resolution | deterministic, explainable, precise | missed aliases |
| Keyed HMAC pseudonyms | stable, not confirmable by hashing guesses | key holders can test candidates; structure still re-identifies |
| Aggregates-only release | nothing person-level published | no person-level analysis for readers |

**With real customer data:** metadata-only connectors so content never leaves the source,
retention schedules, and works council review of questions and thresholds before the first run.

## AI workflow

Built spec-first with GitHub Spec Kit (in `specs/`). A lead agent froze the configuration,
contracts and a synthetic corpus with known answers; ten agents then built one work package each
in parallel worktrees, testing against that ground truth. `make gate` (lint, strict typing, tests,
a privacy canary, an import-boundary test) ran on every change.

Skills used ([`.claude/skills/`](.claude/skills/); detail in
[`docs/ai-workflow.md`](docs/ai-workflow.md)):

- **Spec Kit (SDD):** `speckit-constitution` (seven principles), `speckit-specify` (five user
  stories), `speckit-plan` (zones, contracts), `speckit-tasks` (just over a hundred tasks).
  Implementation ran from `tasks.md` through agent briefs (lead plus ten agents), not the
  `speckit-implement` skill. Planned, not run: `speckit-converge`.
- **Review skills (custom, written for this project):** `data-privacy-review` (caught
  differencing below the minimum group size), `code-quality-review` (strict typing of tests, no
  `Any`), `data-scientist-review` (showed H16 to be a retention artifact).
- **Built-in:** `code-review` (blocked a header reader running into message bodies). Planned, not
  run: `security-review`.

The lead's checks showed H2/H3 to be artifacts; a final review against prior work added the
record change, H25 and attacker A3. A person decided the content line, judged a sample
of real identity merges in a terminal (so real identifiers never entered an AI conversation) and
rejected the artifact results.

## Compared with prior work

Our counts agree with published ones (517,401 files = the 2004 release minus 30 later deletions;
250,537 messages, within 1 % of content-based dedupes); our identity resolution is weaker than
published manual cleanups; within custodians we do not find the published 2001 network changes. Citations: [related work](docs/technical-overview.md#related-work-and-how-this-compares).

## Limits

- Body bytes pass through the decompressor on the way to being skipped; the archive on disk holds them.
- About 150 mailboxes collected by an investigation: what people kept differs by person and period.
- Every crisis comparison crosses the change of the `Date` convention; the placebo windows cannot see it.
- Identity precision on real data rests on a manual sample, not ground truth.
- The noise release is a sketch without a formal privacy budget.

## Next steps

In order; each step is a gate for the next. Details: [technical overview](docs/technical-overview.md#next-steps), [deployment on AWS](docs/deployment-aws.md).

1. **Connectors instead of a file.** The corpus here is a public archive downloaded once; real data
   comes from the customer's tools, pulled through their APIs with OAuth admin consent, the
   narrowest scopes, tokens in a secrets manager, and incremental sync (webhooks or delta queries):
   - **Gmail / Google Workspace:** the `gmail.metadata` scope returns headers but never bodies or
     attachments, so the promise is enforced by Google, not only by our code.
   - **Microsoft 365 (Outlook):** Microsoft Graph `Mail.ReadBasic.All` reads mail without body or
     attachments; Graph Data Connect for bulk export inside the customer's tenant.
   - **Microsoft Teams and Slack:** no metadata-only scope exists; message APIs return text. The
     connector keeps sender, recipients/channel, time and thread IDs and drops the text in memory
     before anything is written, with the canary test extended to cover it. Weaker than a scope,
     so stated as such to the customer.

   Each connector is a new ingest-side package: identifiers stay behind the pseudonymization
   boundary and `Subject` is still discarded at the allowlist.

2. **An API to serve the explorer.** Today the browser fetches one static `release.json`. Replace
   it with a read-only query API: Polars stays the processing engine of the pipeline, which writes
   the release tables as Parquet; DuckDB serves them, querying Parquet in place with no load step.
   Every answer passes the same k ≥ 5 suppression as the release, plus a differencing guard.
3. **Security on the API.** JWT authentication through the customer's own identity provider (IdP: the system their staff
   already sign in with, such as Microsoft Entra ID, Okta or Google Workspace) via OIDC, user roles (viewer,
   analyst, admin) checked on every route, rate limits and a query budget per user and tenant,
   HTTPS only, encrypted storage with per-tenant keys, an audit log of who asked what.
4. **Load and penetration tests** against that architecture: load tests (k6 or Locust) with
   realistic query mixes and tenant counts; an external penetration test; abuse tests that try to
   re-identify people through the API, extending the attacks in `risk/` from releases to queries.
5. **Deploy on AWS**, giving each privacy guarantee a second line in the platform:

```mermaid
flowchart LR
    MAIL["Gmail, Outlook"] -->|"headers only,<br/>scope-enforced"| CON
    CHAT["Teams, Slack"] -->|"text dropped<br/>in memory"| CON
    CI["GitHub Actions<br/>make gate, OIDC,<br/>pulumi up"] -->|signed image| SFN
    KMS{{"customer KMS<br/>HMAC key"}} -.-> SFN
    subgraph W["tenant account · private VPC, egress to provider APIs only"]
        SM{{"Secrets Manager<br/>OAuth tokens, KMS"}} -.-> CON["connectors"]
        CON --> SFN["Step Functions + Fargate<br/>pipeline: Polars"] --> REL[("release Parquet<br/>KMS key per zone")]
        OBS["CloudWatch, Prometheus,<br/>Grafana"]
    end
    subgraph SV["serving account"]
        CF["CloudFront + WAF<br/>static UI, CSP"] -->|"/api, JWT"| API["API Gateway<br/>rate limit, roles"] --> Q["query service<br/>DuckDB, k ≥ 5, budget"]
        Q --> PG[("PostgreSQL<br/>users, roles, audit")]
    end
    REL -->|read-only| Q
    SFN & Q -.->|counts only| OBS
```

   Zones become buckets and IAM roles mirror `zones.ALLOWED`; the key stays in the customer's KMS;
   images are signed only after `make gate`; one account per tenant, residency by region.
   Infrastructure is written with Pulumi in Python, the pipeline's language: typed, tested
   infrastructure, with the IAM policies generated from `zones.ALLOWED` in code.
6. **Analysis:** a record-profile view in the explorer; differential privacy for releases; a
   group-level attack.

## More detail

[Technical overview](docs/technical-overview.md) · [report](release/report.md) ·
[decision record](docs/decision-record.md) · [AI workflow](docs/ai-workflow.md) ·
[specification, plan and tasks](specs/001-enron-network-analysis/)
