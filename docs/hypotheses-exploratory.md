# Exploratory hypotheses E1–E10

> **Numbering (added later).** These hypotheses are now numbered as one list with the
> pre-registered ones: **E*n* is H*n*+4** (E1 = H5 … E12 = H16 … E20 = H24). This file keeps the
> original E-numbers because it is the dated record of when each was stated; the code, the release
> tables, the report and the UI use H5–H24.

**Status: stated and committed before any of them was computed.** This is a second, exploratory
family, added after the pre-registered family H1–H4 (`docs/hypotheses.md`) produced no finding.
It is reported as exploratory. Its design answers the two artifacts that explained H2 and H3:

- **Composition** (who is in the data changes over time): every hypothesis compares each
  custodian with themselves. The statistic is a paired, within-person difference.
- **Volume and retention** (how much mail each person kept differs by period): every measure is
  a ratio or a rate per active week, never a raw count.
- **Hindsight in choosing the change point**: windows are fixed by public dates, not searched for
  in the data.

## Windows

| Name | Dates | Role |
|------|-------|------|
| Crisis (W1) | 2001-08-14 to 2001-12-02 | CEO resignation announced to Chapter 11 filing |
| Reference (W0) | 2000-08-14 to 2000-12-02 | same calendar weeks one year earlier (controls for season) |
| Placebo after (P1) | 2001-01-01 to 2001-04-30 | before any public crisis event |
| Placebo before (P0) | 2000-01-01 to 2000-04-30 | same calendar weeks one year earlier |

Local time is Houston (UTC−6, UTC−5 from April to October); timestamps are hour-resolution.

## Units

Custodians (the collected mailboxes): internal persons with `is_custodian`. A custodian enters a
comparison only with at least 20 messages (sent or received, as the hypothesis needs) in each of
the two windows compared.

## Hypotheses

Sent-side measures use each custodian's sent messages (one row per message, `msg_pid`), all
recipients, including mailings excluded from the network. Received-side measures use messages
in which the custodian is a recipient.

| ID | Measure per custodian and window | Direction in crisis | Reasoning |
|----|----------------------------------|---------------------|-----------|
| E1 | share of sent messages sent outside 07:00–19:00 local on weekdays | up | crisis work spills into evenings |
| E2 | share of sent messages sent on Saturday or Sunday | up | crisis work spills into weekends |
| E3 | share of sent messages with at least one Bcc recipient | up | more discreet copying |
| E4 | share of sent messages with at least one Cc recipient | up | more copying for the record |
| E5 | mean number of recipients per sent message | up | more one-to-many communication |
| E6 | share of sent messages with five or more recipients | up | more one-to-many communication |
| E7 | distinct internal contacts per active week (sent) | down | networks contract under stress |
| E8 | sent messages per active week | up | activity surge |
| E9 | share of sent messages that go to the custodian's three most frequent recipients in that window | up | attention narrows to a few people |
| E10 | share of received messages that came with 20 or more recipients | up | more broadcast communication from the organization |

A week is active for a custodian if it holds at least one of their messages of the kind measured.

## Test and decision rule

For each hypothesis, the paired difference d = measure(W1) − measure(W0) per custodian.

- **Statistic**: median of d; 95% bootstrap interval over custodians (seeded, 2,000 draws).
- **p-value**: Wilcoxon signed-rank test on d, two-sided; Holm correction across E1–E10. *(Superseded when the second family was stated: Holm runs across E1–E20.)*
- **Placebo**: the same difference for P1 − P0, before any crisis event.
- **Leave one out**: the median of d recomputed without each custodian in turn.

**Confident** only if all hold:

1. Holm-adjusted p < 0.05;
2. the interval lies wholly on the hypothesised side of zero;
3. placebo: its interval includes zero, or its median is less than half the crisis median on the
   same side (a pre-existing trend would otherwise explain the change);
4. every leave-one-out median has the hypothesised sign.

Otherwise the outcome is *not supported* or *inconclusive*, and is reported as such. All ten
outcomes are published, whatever they are.

## Known limits

- Custodians are mostly senior staff; results describe them, not the whole organization.
- Timestamps were normalised to Pacific time in the corpus and are hour-resolution; E1 and E2
  inherit that resolution.
- E3 depends on Bcc being visible, which it is only in the sender's own copy; sent-side measures
  use exactly those copies.
- This family is exploratory. A confident result here is a lead for confirmation on other data,
  not a pre-registered finding.
- *(Added after the data-science review.)* The placebo windows (January–April) hold less mail
  than the crisis and reference windows, so fewer custodians meet the minimum of 20 messages:
  in the last committed real run about half as many (`placebo_custodians` against `custodians`
  in `release/exploratory.csv`, e.g. 15 against 32 for the sent-side measures). The placebo
  therefore has lower power than the crisis comparison, and its custodians are a subset that
  may differ from those compared in the crisis. A passing placebo (interval covering zero) does
  not exclude a pre-existing trend; it only fails to detect one.

---

# Second exploratory family E11–E20

**Status: stated and committed before any of them was computed, after E1–E10 were computed.**
E1–E10 produced no confident result. They showed that hour-of-day measures are unreliable in this
corpus (the 2000 timestamps are shifted by several hours) and that Bcc carries no information
(every Bcc line repeats the Cc line). This family avoids both. It uses the same windows, units,
minimum of 20 messages, test and decision rule as E1–E10, with one change: **Holm's correction runs
across all twenty exploratory hypotheses, E1–E20**, so adding hypotheses makes each one harder to
pass, not easier.

E11 is not independent of what was seen: it is derived from the unexpected E10 result (custodians
received a smaller share of broadcast mail in the crisis). It is marked as derived and must be
read as a consistency check on a lead, not as a fresh test.

| ID | Measure per custodian and window | Direction in crisis | Reasoning |
|----|----------------------------------|---------------------|-----------|
| E11 | share of sent messages with exactly one recipient | up | *derived from E10*: more direct, one-to-one mail |
| E12 | share of the custodian's sent-to contacts who also sent to the custodian in the same window | up | ties become mutual under stress |
| E13 | share of sent messages addressed to at least one other custodian | up | senior staff turn to each other |
| E14 | share of received messages sent by another custodian | up | the same, seen from the inbox |
| E15 | share of the window's distinct contacts not contacted in the 26 weeks before the window | down | less reaching out to new people |
| E16 | distinct senders per active week (received) | up | more people reach out to the custodian |
| E17 | share of received messages that come from the custodian's three most frequent senders | up | attention concentrates on a few senders |
| E18 | share of received messages from external senders | down | outsiders drop away |
| E19 | share of weeks in the window with at least one sent message | up | more consistently active |
| E20 | share of sent messages that include a non-person recipient (list, role or system address) | down | less routine, list-based traffic |

Received-side measures (E14, E16, E17, E18) use messages in which the custodian is a recipient;
the others use sent messages. E15 looks back 26 weeks before each window's start.

---

## Implementation notes (after code review, before any rerun)

A code review of the implementation found measurement details that did not match the text above;
they were fixed so the code measures what was stated:

- **E1** is the share among *weekday* messages (weekend volume no longer moves it). E1 remains
  invalid for the timestamp reason above.
- **Local time** uses the actual US daylight-saving switch dates, not April–October by month.
- **E19** counts only full Monday-to-Sunday weeks inside each window, in numerator and
  denominator, so partial edge weeks cannot lower it.
- A placebo with **no change at all** (every difference zero) now counts as passing; before, it
  was treated as undefined and failed.
- **Caveats** are recorded in the results and block a "confident" outcome: E1 (timestamp shift),
  E3 (Bcc repeats Cc), E15 (the 26-week look-back depends on how much older mail was kept).
- Parameters (minimum messages, bootstrap draws, alpha) are `Config` fields.

## Checks added after results were seen

**Written after the results of E1–E20 were known, and says so.** Two checks were added to this
family after its results, so they are post hoc. They can only stop a hypothesis from being held
true; neither can make one confident.

- **Mail-volume equalisation** (870f808, after E12 came out confident on the first computation).
  For every hypothesis not rejected and without a caveat, each custodian's sent and received
  messages in both windows are subsampled to the smaller window's count, the measure is
  recomputed and the paired test rerun. It is reported next to the outcome, not part of the
  rule. Because it is run only for the hypotheses that survived, its p has no Holm rank of its
  own: `equalised_p_holm` multiplies it by the family size (20) and caps it at 1, which is Holm's
  multiplier for the family's smallest p and conservative at every other rank. Read the
  equalised result against `equalised_p_holm`, not the unadjusted `equalised_p`.
- **Retention check** (2703cba, after the data-science review, run with the
  `/data-scientist-review` skill). Inbox retention differs by person and period, so a contact's
  message can be missing because the custodian's inbox lost it. E12 is recomputed counting only
  contacts who are themselves custodians, whose messages survive in their own sent folders
  whatever the receiving inbox kept; crisis against reference with the same placebo. It passes
  only if the crisis interval lies on the hypothesised side over at least k custodians and the
  placebo passes; a hypothesis that fails it is at most inconclusive. E12 fails it: among
  custodian-to-custodian contacts the change is not established, and the same subset rises
  before the crisis. No hypothesis in E1–E20 is held true. The check is defined for E12 only.
  The same threat applies to the other received-side measures (E10, E14, E16–E18), but none of
  them was held true (in the last committed real run E16 is inconclusive and the others are not
  supported), and a failed check can only cap an outcome at inconclusive, so it could not change
  theirs. A future run in which one of them is held true needs its own retention check first.

E12 measures whether a contact sent the custodian anything in the same window, not whether they
replied: headers carry no thread.

---

# Post-hoc hypothesis E21 (= H25): a replication test of prior work

**Status: post hoc. Stated and committed on 2026-11-14, after every result of H1–H24 was known
and after prior work on the corpus was read, and before E21 was computed.** It is not a fresh
prediction of ours: it tests, at the scope our design can defend, the best-known published result
on how this network changed in 2001. Diesner, Frantz & Carley (2005) compare monthly networks
among Enron employees and report that during the crisis the network became denser and more
connected. Our pre-registered H1–H4 do not test density, and the network-level density of the
observed or core network moves with how much mail was kept, so it cannot be read as behaviour.

| ID | Measure per custodian and window | Direction in crisis | Reasoning |
|----|----------------------------------|---------------------|-----------|
| E21 | share of the other custodians with whom the custodian exchanged at least one message, in either direction, in the window (core ego density; any surviving copy counts) | up | Diesner, Frantz & Carley (2005): denser, more connected communication in the crisis |

- **Units, windows, test and rule**: exactly as E1–E20 (crisis against the same weeks a year
  earlier; pre-crisis placebo; leave-one-out; Wilcoxon signed-rank; median with a bootstrap
  interval). A custodian enters with at least 20 sent **and** 20 received messages in each window
  (n is the smaller of the two counts). The denominator is the number of custodians minus one.
- **Multiple testing**: Holm's correction runs across E1–E21 (H5–H25, twenty-one hypotheses), so
  adding E21 makes every hypothesis harder to pass, not easier.
- **Retention check**: the same measure counting only the custodians this custodian *sent* to,
  which no inbox can move. It must pass as the E12 check does (crisis interval on the
  hypothesised side over at least k custodians, and the placebo passes), or E21 is at most
  inconclusive.
- **Volume equalisation** is reported next to it, as for the others.
- **Known threat stated before computing**: a monthly profile of custodians' sent mail (published
  as `release/record_profile.csv`) shows that the hour-of-day convention of the `Date` header
  changes between May and August 2001, consistent with a change of mail system. The crisis
  window lies after that change and the reference window before it; the placebo windows both lie
  before it. Any E21 outcome, like every E1–E20 outcome, compares two recording regimes, and
  the placebo cannot detect an artifact of that change. A confident E21 would therefore be
  reported as a lead, not as a finding.

## E21 result (written after it was computed)

E21 (H25) is **not supported**: median within-custodian change +0.008 (interval 0 to 0.033) over
31 custodians, Holm-adjusted p 0.24 across the twenty-one, and the pre-crisis placebo shows a
change of the same size (+0.025, 13 custodians). Its retention check did not run, because the
outcome was not supported (a check can only cap an outcome). The published densification is not
visible when each custodian is compared with themselves a year earlier. Numbers:
`release/exploratory.csv`, row H25.

The record profile stated as a known threat above is published as `release/record_profile.csv`
and summarised in the report ("What changed in the record during the crisis year"): the
after-hours share of the custodians' weekday sent mail lies between about 0.43 and 0.54 in the
reference months and between 0.04 and 0.06 in the crisis months, and from May 2001 on every month
lies below every earlier month. The placebo windows (January–April 2000 and 2001) both lie
before that change, so a passing placebo cannot clear any H5–H25 result of it.
