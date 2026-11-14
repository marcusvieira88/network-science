# Exploratory hypotheses E1–E10

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
- **p-value**: Wilcoxon signed-rank test on d, two-sided; Holm correction across E1–E10.
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
