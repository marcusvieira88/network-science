# Architecture

How data flows through the pipeline, where the privacy boundary sits, and how the explorer UI is
fed. Kept in step with the code; the source of the design is
`specs/001-enron-network-analysis/plan.md` and `research.md`.

### Data zones and stages

```mermaid
flowchart TB
    subgraph RAW["Zone 0 · raw (git-ignored)"]
        A[(Corpus archive<br/>sha256 pinned)]
    end
    subgraph ING["Zone 1 · ingest — identifiers allowed, purged at end of run"]
        S1[S1 parse<br/>headers only, allowlist]
        S2[S2 clean + dedupe]
        S3[S3 resolve identities]
        T1[(header_records)]
        T2[(messages)]
        T3[(entities + address_map)]
    end
    subgraph RES["Zone 2 · restricted — pseudonyms only (git-ignored)"]
        S4[S4 pseudonymize<br/>HMAC, key from outside repo]
        T4[(events + entities_p)]
        S5[S5 network snapshots + metrics]
        S6[S6 hypotheses + statistics]
        S7[S7 re-identification attack]
        T5[(snapshots + metric series)]
    end
    subgraph REL["Zone 3 · release — aggregates, k ≥ 5 (committed)"]
        S8[S8 k-threshold + mitigation]
        T8[(release tables)]
        S9[S9 report, decision record, slides]
    end
    K{{Key}} -.-> S4
    A --> S1 --> T1 --> S2 --> T2 --> S3 --> T3 --> S4 --> T4
    T4 --> S5 --> T5 --> S6 --> S8
    T4 --> S7 --> S8
    T5 --> S7
    S8 --> T8 --> S9
    T3 -. truth for scoring only, counts out .-> S7
    S1 & S2 & S3 -. counts only .-> Q[(quality metrics)] --> S8
```

Three rules make the picture enforceable:

1. A package may open files only in its allowed zones (`zones.py` path guard).
2. Packages right of the boundary may not import packages left of it (AST test).
3. Only S8 writes to `release/`, and it refuses any table with a group below k.

### One-command run

```mermaid
sequenceDiagram
    actor Rev as Reviewer
    participant M as make all
    participant P as Pipeline
    participant Z1 as Ingest zone
    participant Z2 as Restricted zone
    participant Z3 as release/
    Rev->>M: make all
    M->>P: uv sync (locked), key present?
    alt no key
        P-->>Rev: stop: run "make key" (writes outside repo)
    end
    P->>P: fetch archive, verify sha256
    P->>Z1: S1–S3 parse, clean, resolve
    P->>Z2: S4 pseudonymize
    P->>Z2: S5–S7 network, hypotheses, attack
    P->>Z3: S8 thresholded tables
    P->>Z3: S9 report + docs numbers
    P->>Z1: purge ingest zone
    P->>P: write run_manifest.json (fingerprints, seed)
    M->>P: make gate (lint, types, tests, canary)
    P-->>Rev: release/report.md
```

### Identity resolution and pseudonymization

```mermaid
flowchart LR
    O[Address + name observations] --> N1[N1 normalize]
    N1 --> N2[N2 org subdomains]
    N2 --> N3[N3 sender name link<br/>support ≥ 3 + pattern]
    N3 --> N4[N4 legacy directory forms]
    N4 --> G{Guards:<br/>name only? cross-org?<br/>generic local part?}
    G -- blocked --> X[keep separate, count]
    G -- ok --> U[Union-find cluster<br/>merge tagged with rule]
    U --> TY[Type: person / list / system / role]
    TY --> C[canonical_id = smallest address]
    C --> H[HMAC-SHA256 subkey person-v1]
    H --> P[pseudonym p_…]
    U --> EV[precision / recall vs ground truth]
```

### Analysis and evidence

```mermaid
flowchart TB
    H0[docs/hypotheses.md<br/>H1–H4 committed first] --> RUN
    E[(events)] --> W[weekly snapshots<br/>core + observed scope]
    W --> MS[metric series]
    MS --> RUN[per hypothesis]
    RUN --> CP[change point + permutation p]
    RUN --> ES[effect size + block bootstrap CI]
    RUN --> NM[null model: rewire within week]
    RUN --> RB[robustness: leave-one-mailbox-out,<br/>recipient cap, window]
    CP & ES & NM & RB --> HC[Holm correction]
    HC --> D{passes all?}
    D -- yes --> F[headline finding + confidence]
    D -- no --> NS[reported as not supported]
    F & NS --> T[(hypotheses table → release)]
```

### Re-identification test

```mermaid
flowchart LR
    subgraph Attacker["Attacker side — no access to truth"]
        AUX1[A1: features from public raw corpus<br/>naive parse, per address]
        AUX2[A2: a few known seeds + contacts]
        ATT[matching / seed propagation]
    end
    R0[(R0 node-level<br/>pseudonymized edges)] --> ATT
    R1[(R1 aggregates, k ≥ 5,<br/>bucketed, no pseudonyms)] --> ATT
    R2[(R2 = R1 + noise)] --> ATT
    AUX1 --> ATT
    AUX2 --> ATT
    ATT --> GZ[guesses]
    GZ --> SC[scorer in ingest zone<br/>counts only]
    SC --> RT[(risk table:<br/>uniqueness, re-id rate,<br/>utility loss per release)]
    R1 --> UT[recompute headline finding] --> RT
```

### Explorer UI

```mermaid
flowchart LR
    subgraph REL["Zone 3 · release (k ≥ 5, no pseudonyms)"]
        T8[(release tables<br/>incl. community_graph.csv)]
    end
    T8 --> S10[S10 ui-data<br/>uiexport: CSV → one JSON,<br/>re-checked for identifiers]
    S10 --> J[(ui/public/data/release.json)]
    J --> APP[React app · shadcn/ui · dark]
    subgraph Views
        V1[Overview<br/>headline finding, key numbers]
        V2[Metrics over time<br/>metric / scope / variant toggles,<br/>change point, event markers, interval band]
        V3[Network over time<br/>groups as nodes, ties between groups,<br/>week slider + play]
        V4[Hypotheses H1–H4]
        V5[Data quality<br/>cleaning funnel, header ruling]
        V6[Privacy and risk<br/>R0 / R1 / R2 before and after]
        V7[Limits]
    end
    APP --> V1 & V2 & V3 & V4 & V5 & V6 & V7
```

Rules for the UI:

1. It is a static site. Its only input is `release.json`, produced from `release/` alone, so it
   cannot show anything the report could not.
2. The network view draws **groups** (baseline communities with at least k members) and the
   weekly tie weight between them. There is no person-level node, tooltip or table anywhere.
3. No outside requests: fonts and assets are bundled; no analytics, no CDN. A test scans the
   build for external URLs.
4. `make all` does not need Node. `make ui` builds and serves the interface after a run.
